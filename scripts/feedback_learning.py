# -*- coding: utf-8 -*-
"""피드백 학습 폐루프 — 👍/👎 결과를 주기적으로 학습/개선에 자동 반영(A1).

흐름:
  1) 👍(고평점) 사주 상담 답변 → Claude로 '개인정보·특정 명식 제거한 일반 명리 지식' 추출
     → 검증 코퍼스로 색인(trust tier1) → 유사 질문이 검증된 해석을 retrieval.
  2) 👎(+코멘트) → data/feedback/review_queue.jsonl 에 적재(자료보충·프롬프트 보강 검토용).
  3) 처리한 피드백은 learned=True 로 표시(중복 학습 방지).
  4) 타로 피드백(source=tarot): 타로는 RAG(검색)를 쓰지 않으므로 👍를 코퍼스에 색인하지 않는다.
     👎 → 동일 개선 큐(덱 키워드/해석·프롬프트 보강 검토용), 👍 → 집계 + learned 마킹만.
     (chat 만 처리하던 사각지대 보완 — tool·compat 은 추후 동일 방식 확장 여지.)

안전장치: 개인 사주 유출·명식 특이성은 Claude 일반화로 제거. fitz 미사용(torch 단독 프로세스 OK).
배치(외부 Claude API)라 GPU 경합 없음.

사용:
  .venv\\Scripts\\python.exe -m scripts.feedback_learning [--limit 50] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

FB_DIR = PROJECT_ROOT / "data" / "feedback"
VERIFIED_DIR = FB_DIR / "verified"
REVIEW_QUEUE = FB_DIR / "review_queue.jsonl"


def _question_for(db, msg) -> str | None:
    """assistant 메시지 직전의 user 메시지(질문)를 같은 세션에서 찾는다."""
    from sqlalchemy import select
    from backend.app.repositories.models import ChatMessage
    q = db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == msg.session_id,
            ChatMessage.role == "user",
            ChatMessage.id < msg.id,
        ).order_by(ChatMessage.id.desc()).limit(1)
    ).scalars().first()
    return q.content.strip() if q and q.content else None


def _tarot_question_for(db, msg) -> str | None:
    """타로 답변 메시지의 세션 질문(TarotSession.question)을 찾는다."""
    if msg is None:
        return None
    from backend.app.repositories.models import TarotSession
    sess = db.get(TarotSession, msg.tarot_id)
    return (sess.question or "").strip() if sess and sess.question else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from sqlalchemy import select
    from backend.app.core.db import get_session_factory
    from backend.app.repositories.auth_models import MessageFeedback
    from backend.app.repositories.models import ChatMessage, TarotMessage
    from backend.app.services import external_llm

    FB_DIR.mkdir(parents=True, exist_ok=True)
    VERIFIED_DIR.mkdir(parents=True, exist_ok=True)

    sf = get_session_factory()
    verified_paths: list[tuple[Path, str]] = []  # (txt_path, source)
    down_count = 0
    tarot_up = 0
    learned_ids: list[int] = []

    with sf() as db:
        rows = db.execute(
            select(MessageFeedback).where(
                MessageFeedback.source == "chat",
                MessageFeedback.learned.is_(False),
            ).order_by(MessageFeedback.id).limit(args.limit)
        ).scalars().all()
        print(f"[fb] 미처리 chat 피드백 {len(rows)}건")

        for fb in rows:
            if fb.rating > 0:  # 👍 → 검증 지식 추출
                msg = db.get(ChatMessage, fb.message_id)
                if msg is None or msg.role != "assistant" or not (msg.content or "").strip():
                    learned_ids.append(fb.id); continue
                if len((msg.content or "")) < 200:  # 너무 짧으면 학습가치 낮음
                    learned_ids.append(fb.id); continue
                question = _question_for(db, msg) or "(질문 미상)"
                know = external_llm.generalize_verified_knowledge(question, msg.content.strip())
                if not know:
                    print(f"   [👍 {fb.id}] 일반화 지식 없음 — 건너뜀")
                    learned_ids.append(fb.id); continue
                src = f"fb_verified_{fb.id}"
                txt = VERIFIED_DIR / f"{src}.txt"
                txt.write_text(f"[검증된 명리 해석 — 👍]\n{know}\n", encoding="utf-8")
                verified_paths.append((txt, src))
                learned_ids.append(fb.id)
                print(f"   [👍 {fb.id}] 검증지식 추출 {len(know)}자 → {src}")
            elif fb.rating < 0:  # 👎 → 개선 큐
                msg = db.get(ChatMessage, fb.message_id)
                question = _question_for(db, msg) if msg else None
                rec = {"fid": fb.id, "message_id": fb.message_id, "source": fb.source,
                       "question": question, "comment": fb.comment,
                       "created_at": fb.created_at.isoformat() if fb.created_at else None,
                       "queued_at": datetime.utcnow().isoformat()}
                if not args.dry_run:
                    with open(REVIEW_QUEUE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                down_count += 1
                learned_ids.append(fb.id)

        # ── 타로 피드백: 👎→개선 큐, 👍→집계만(코퍼스 미색인 — 타로는 RAG 비사용) ──
        trows = db.execute(
            select(MessageFeedback).where(
                MessageFeedback.source == "tarot",
                MessageFeedback.learned.is_(False),
            ).order_by(MessageFeedback.id).limit(args.limit)
        ).scalars().all()
        print(f"[fb] 미처리 tarot 피드백 {len(trows)}건")
        for fb in trows:
            if fb.rating < 0:  # 👎 → 개선 큐(덱 해석·프롬프트 보강 검토용)
                msg = db.get(TarotMessage, fb.message_id)
                question = _tarot_question_for(db, msg)
                rec = {"fid": fb.id, "message_id": fb.message_id, "source": fb.source,
                       "question": question, "comment": fb.comment,
                       "created_at": fb.created_at.isoformat() if fb.created_at else None,
                       "queued_at": datetime.utcnow().isoformat()}
                if not args.dry_run:
                    with open(REVIEW_QUEUE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                down_count += 1
            else:  # 👍 → 코퍼스 미색인(타로는 검색 비사용). 집계·learned 마킹만.
                tarot_up += 1
            learned_ids.append(fb.id)

        if args.dry_run:
            print(f"[fb][dry-run] 👍검증 {len(verified_paths)} · 👎큐 {down_count} · 타로👍 {tarot_up} (색인·표시 안 함)")
            return 0

        # 검증 지식 색인(trust=True — 신뢰 소스, 청크 게이트 우회)
        added = 0
        if verified_paths:
            from ml.data_pipeline.ingest_rag import source_meta  # noqa: F401  (참고용)
            from scripts.nightly_learning import _embed_and_upsert
            paths = [p for p, _src in verified_paths]
            src_map = {p.stem: s for p, s in verified_paths}
            added = _embed_and_upsert(
                paths,
                source_fn=lambda p: {"source": src_map.get(p.stem, p.stem), "category": "verified_feedback"},
                label="검증피드백 색인", stage="index", trust=True,
            )

        # learned 표시(중복 학습 방지)
        if learned_ids:
            for fb in db.execute(
                select(MessageFeedback).where(MessageFeedback.id.in_(learned_ids))
            ).scalars():
                fb.learned = True
            db.commit()

    print(f"[fb] 완료 — 👍검증지식 색인 {added} chunks ({len(verified_paths)}건) · 👎개선큐 {down_count}건(타로 포함) · 타로👍 {tarot_up}건(집계) · learned 표시 {len(learned_ids)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
