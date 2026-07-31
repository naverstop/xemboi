# -*- coding: utf-8 -*-
"""일일 사용자 질문 인사이트 배치 (CPU 전용).

지난 N시간(기본 24h)의 사용자 질문을 모아:
  1) PII 마스킹 → bge-m3(CPU) 임베딩 → 코사인 그리디 클러스터링으로 토픽 묶음
  2) Qdrant saju_corpus 대비 커버리지 점수(갭 분석) — retrieval_logs + 직접 질의
  3) message_feedback(👍👎/코멘트) 연계 만족도 집계
  4) Claude API(haiku) 1회 호출로 클러스터 라벨 + 개선 제안 생성 (키 없으면 키워드 폴백)
  → output/reports/question_insight_YYYYMMDD.md / .json 리포트 저장

GPU를 사용하지 않는다: 임베딩은 device="cpu" 강제, LLM은 외부 API.
서비스 Ollama(GPU 상주 모델)는 절대 건드리지 않는다.

실행:
  python -m scripts.daily_question_insight [--hours 24] [--no-llm] [--threshold 0.62]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# CPU 강제 — torch가 GPU를 잡지 않도록 import 전에 차단
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # "" 은 torch 에서 무효 → "-1" 로 GPU 차단(CPU 전용)

from sqlalchemy import select  # noqa: E402

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.db import get_session_factory  # noqa: E402
from backend.app.repositories.auth_models import MessageFeedback  # noqa: E402
from backend.app.repositories.models import ChatMessage, RetrievalLog  # noqa: E402

# ---------------- PII 마스킹 ----------------

_PII_PATTERNS = [
    (re.compile(r"\d{4}\s*[-./년]\s*\d{1,2}\s*[-./월]\s*\d{1,2}\s*일?"), "[생년월일]"),
    (re.compile(r"\d{2,4}\s*년\s*\d{1,2}\s*월(\s*\d{1,2}\s*일)?"), "[생년월일]"),
    (re.compile(r"01[016789]\s*[-.]?\s*\d{3,4}\s*[-.]?\s*\d{4}"), "[전화번호]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[이메일]"),
    (re.compile(r"\d{6}\s*[-]\s*\d{7}"), "[주민번호]"),
]


def mask_pii(text: str) -> str:
    for pat, repl in _PII_PATTERNS:
        text = pat.sub(repl, text)
    return text.strip()


# ---------------- 데이터 수집 ----------------

def collect(db, since: datetime) -> list[dict]:
    """user 질문 + 직후 assistant 답변 + 피드백 + retrieval 점수를 한 레코드로."""
    msgs = db.execute(
        select(ChatMessage)
        .where(ChatMessage.created_at >= since)
        .order_by(ChatMessage.session_id, ChatMessage.id)
    ).scalars().all()

    records: list[dict] = []
    for i, m in enumerate(msgs):
        if m.role != "user":
            continue
        reply = None
        for n in msgs[i + 1:]:
            if n.session_id != m.session_id:
                break
            if n.role == "assistant":
                reply = n
                break
            if n.role == "user":
                break
        records.append({
            "session_id": m.session_id,
            "question_raw": m.content,
            "question": mask_pii(m.content)[:500],
            "created_at": m.created_at.isoformat(),
            "answer_id": reply.id if reply else None,
            "answer_len": len(reply.content) if reply else 0,
            "n_sources": len(reply.sources_json or []) if reply else 0,
        })

    # 피드백 연결
    aids = [r["answer_id"] for r in records if r["answer_id"]]
    fb_map: dict[int, list] = {}
    if aids:
        for fb in db.execute(
            select(MessageFeedback).where(MessageFeedback.message_id.in_(aids))
        ).scalars().all():
            fb_map.setdefault(fb.message_id, []).append(fb)
    for r in records:
        fbs = fb_map.get(r["answer_id"] or -1, [])
        r["fb_up"] = sum(1 for f in fbs if f.rating > 0)
        r["fb_down"] = sum(1 for f in fbs if f.rating < 0)
        r["fb_comments"] = [f.comment for f in fbs if f.comment]

    # retrieval_logs 연결 (같은 세션 + 같은 질문 prefix)
    rlogs = db.execute(
        select(RetrievalLog).where(RetrievalLog.created_at >= since)
    ).scalars().all()
    rmap = {(rl.session_id, rl.question[:120]): rl for rl in rlogs}
    for r in records:
        rl = rmap.get((r["session_id"], r["question_raw"][:120]))
        r["rag_max_score"] = rl.max_score if rl else None
    return records


# ---------------- 클러스터링 (그리디 코사인) ----------------

def cluster(records: list[dict], threshold: float) -> list[list[int]]:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    s = get_settings()
    model = SentenceTransformer(s.embed_model, device="cpu")
    vecs = model.encode(
        [r["question"] for r in records],
        normalize_embeddings=True, convert_to_numpy=True, batch_size=16,
        show_progress_bar=False,
    )
    for r, v in zip(records, vecs):
        r["_vec"] = v

    centroids: list = []
    members: list[list[int]] = []
    for idx, v in enumerate(vecs):
        best, best_sim = -1, threshold
        for ci, c in enumerate(centroids):
            sim = float(np.dot(v, c) / (np.linalg.norm(c) + 1e-9))
            if sim > best_sim:
                best, best_sim = ci, sim
        if best >= 0:
            members[best].append(idx)
            n = len(members[best])
            centroids[best] = centroids[best] * ((n - 1) / n) + v / n
        else:
            centroids.append(v.copy())
            members.append([idx])
    return sorted(members, key=len, reverse=True)


# ---------------- 코퍼스 커버리지 (갭 분석) ----------------

def coverage(records: list[dict]) -> None:
    """retrieval_logs가 없는 질문(basic 깊이 등)은 Qdrant에 직접 질의해 보충."""
    s = get_settings()
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=s.qdrant_url, timeout=15.0)
        for r in records:
            if r["rag_max_score"] is not None:
                continue
            res = client.query_points(
                collection_name=s.qdrant_collection,
                query=r["_vec"].tolist(), limit=3, with_payload=False,
            ).points
            r["rag_max_score"] = max((p.score for p in res), default=0.0)
    except Exception as e:  # noqa: BLE001 — Qdrant 다운 시 갭 분석만 생략
        print(f"[warn] Qdrant 커버리지 보충 실패: {e}")


# ---------------- 라벨링/제안 (Claude 1회 호출 또는 키워드 폴백) ----------------

_STOPWORDS = {
    "있나요", "있을까요", "어떤가요", "어떻게", "알려줘", "알려주세요", "궁금합니다",
    "궁금해요", "해주세요", "있는지", "대해서", "대해", "관련", "제가", "저는", "혹시",
    "그리고", "하면", "할까요", "좋을까요", "되나요", "인가요", "사주", "올해", "내년",
}


def keyword_label(qs: list[str]) -> str:
    words = Counter()
    for q in qs:
        for w in re.findall(r"[가-힣]{2,}", q):
            if w not in _STOPWORDS:
                words[w] += 1
    return " · ".join(w for w, _ in words.most_common(3)) or "(미분류)"


def llm_analyze(clusters_meta: list[dict], model: str) -> dict | None:
    """Claude 1회 호출 — 클러스터 라벨 + 운영 개선 제안. 실패 시 None."""
    s = get_settings()
    api_key = getattr(s, "anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        payload = json.dumps(clusters_meta, ensure_ascii=False, indent=1)
        prompt = f"""사주 상담 챗봇의 지난 24시간 사용자 질문 클러스터 분석 결과입니다.
coverage는 학습 코퍼스(Qdrant) 최대 유사도(0~1, 낮을수록 자료 부족), fb_down은 👎 수입니다.

{payload}

JSON으로만 답하세요:
{{"labels": {{"<cluster_id>": "<8자 내외 토픽명>"}},
 "gaps": ["코퍼스 자료 보강이 필요한 주제와 추천 자료 유형 (커버리지 낮은 순)"],
 "faq_candidates": ["FAQ로 만들면 좋을 빈출 질문"],
 "answer_improvements": ["👎 패턴/코멘트 기반 답변 개선 제안"],
 "summary": "오늘의 핵심 인사이트 2~3문장"}}"""
        resp = client.messages.create(
            model=model, max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Claude 분석 실패(키워드 폴백 사용): {e}")
        return None


# ---------------- 리포트 ----------------

def build_report(records, clusters, analysis, hours: int) -> tuple[str, dict]:
    now = datetime.now()
    total = len(records)
    n_sessions = len({r["session_id"] for r in records})
    up = sum(r["fb_up"] for r in records)
    down = sum(r["fb_down"] for r in records)
    fb_rate = (up + down) / total * 100 if total else 0.0

    cluster_rows = []
    for ci, idxs in enumerate(clusters):
        qs = [records[i]["question"] for i in idxs]
        covs = [records[i]["rag_max_score"] for i in idxs if records[i]["rag_max_score"] is not None]
        cov = sum(covs) / len(covs) if covs else None
        label = (analysis or {}).get("labels", {}).get(str(ci)) or keyword_label(qs)
        cluster_rows.append({
            "cluster_id": ci,
            "label": label,
            "size": len(idxs),
            "coverage": round(cov, 3) if cov is not None else None,
            "fb_up": sum(records[i]["fb_up"] for i in idxs),
            "fb_down": sum(records[i]["fb_down"] for i in idxs),
            "questions": qs[:10],
            "fb_comments": [c for i in idxs for c in records[i]["fb_comments"]][:10],
        })

    gaps = sorted(
        (c for c in cluster_rows if c["coverage"] is not None),
        key=lambda c: c["coverage"],
    )[:5]

    md = [f"# 일일 질문 인사이트 — {now:%Y-%m-%d %H:%M} (최근 {hours}h)\n"]
    md.append(f"- 질문 수: **{total}** (세션 {n_sessions}개)")
    md.append(f"- 피드백: 👍 {up} / 👎 {down} (참여율 {fb_rate:.1f}%)\n")
    if analysis and analysis.get("summary"):
        md.append(f"> **핵심 인사이트**: {analysis['summary']}\n")

    md.append("## 토픽 클러스터\n")
    md.append("| # | 토픽 | 질문수 | 코퍼스 커버리지 | 👍 | 👎 |")
    md.append("|---|------|-------|----------------|----|----|")
    for c in cluster_rows[:20]:
        cov = f"{c['coverage']:.3f}" if c["coverage"] is not None else "-"
        md.append(f"| {c['cluster_id']} | {c['label']} | {c['size']} | {cov} | {c['fb_up']} | {c['fb_down']} |")

    md.append("\n## 코퍼스 갭 (자료 보강 필요 순)\n")
    for c in gaps:
        md.append(f"- **{c['label']}** (커버리지 {c['coverage']}, 질문 {c['size']}건) — 예: \"{c['questions'][0]}\"")
    if analysis:
        for g in analysis.get("gaps", []):
            md.append(f"- 💡 {g}")

    if analysis and analysis.get("faq_candidates"):
        md.append("\n## FAQ 후보\n")
        for q in analysis["faq_candidates"]:
            md.append(f"- {q}")

    md.append("\n## 답변 개선 제안\n")
    neg_comments = [c for r in records for c in r["fb_comments"] if r["fb_down"]]
    if analysis:
        for a in analysis.get("answer_improvements", []):
            md.append(f"- {a}")
    if neg_comments:
        md.append("\n### 👎 코멘트 원문\n")
        for c in neg_comments[:20]:
            md.append(f"- {c}")
    if not analysis and not neg_comments:
        md.append("- (LLM 분석 비활성 — 👎 코멘트 없음)")

    data = {
        "generated_at": now.isoformat(),
        "window_hours": hours,
        "total_questions": total,
        "sessions": n_sessions,
        "feedback": {"up": up, "down": down, "rate_pct": round(fb_rate, 1)},
        "clusters": cluster_rows,
        "analysis": analysis,
    }
    return "\n".join(md) + "\n", data


def main() -> int:
    ap = argparse.ArgumentParser(description="일일 질문 인사이트 배치 (CPU 전용)")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--threshold", type=float, default=0.72, help="클러스터 코사인 임계값")
    ap.add_argument("--no-llm", action="store_true", help="Claude 분석 생략(키워드 라벨만)")
    ap.add_argument("--claude-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--out", default=str(PROJECT_ROOT / "output" / "reports"))
    args = ap.parse_args()

    since = datetime.utcnow() - timedelta(hours=args.hours)
    db = get_session_factory()()
    try:
        records = collect(db, since)
    finally:
        db.close()
    print(f"[info] 질문 {len(records)}건 수집 (since {since:%Y-%m-%d %H:%M} UTC)")
    if not records:
        print("[info] 분석할 질문 없음 — 종료")
        return 0

    clusters = cluster(records, args.threshold)
    print(f"[info] 클러스터 {len(clusters)}개")
    coverage(records)

    analysis = None
    if not args.no_llm:
        meta = []
        for ci, idxs in enumerate(clusters[:20]):
            covs = [records[i]["rag_max_score"] for i in idxs if records[i]["rag_max_score"] is not None]
            meta.append({
                "cluster_id": str(ci),
                "size": len(idxs),
                "coverage": round(sum(covs) / len(covs), 3) if covs else None,
                "fb_down": sum(records[i]["fb_down"] for i in idxs),
                "sample_questions": [records[i]["question"] for i in idxs[:5]],
                "down_comments": [c for i in idxs for c in records[i]["fb_comments"]][:5],
            })
        analysis = llm_analyze(meta, args.claude_model)

    md, data = build_report(records, clusters, analysis, args.hours)
    for r in records:  # 직렬화 전 벡터 제거
        r.pop("_vec", None)
        r.pop("question_raw", None)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d}"
    md_path = out_dir / f"question_insight_{stamp}.md"
    json_path = out_dir / f"question_insight_{stamp}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 리포트 저장: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
