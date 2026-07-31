# -*- coding: utf-8 -*-
"""명식 정합성 오프라인 회귀 평가 — 대표 명식 × 질문으로 답변의 4주 지지 일치율 측정.

실제 사주 상담 파이프라인(예방 가드 포함)으로 답변을 생성하고:
  · init 일치율  = exaone 1차 답변이 명식과 일치한 비율(예방 효과 측정)
  · final 일치율 = 검증·교정 후 일치한 비율(검증 루프 효과 — 목표 100%)
를 리포트한다. CPU 전용(exaone), 외부 비용 0. 품질 회귀 감시용.

실행: python -m scripts.eval_chart_fidelity [--charts N] [--no-rag]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType
from backend.app.services import chat_service as cs, template_service
from backend.app.core.db import get_session_factory

QUESTIONS = ["직업운을 알려줘", "성격은 어떤가요", "올해 전반적인 운세는", "조후가 잘 이루어져 있나요"]


def _sample_charts(n: int):
    """다양한 명식 n개 — 2000~2014년 사이 여러 날짜·시각."""
    out = []
    base = date(2000, 1, 10)
    step = 277  # 임의 간격으로 분포
    for i in range(n):
        d = base + timedelta(days=step * i)
        bi = BirthInput(birth_date=d, birth_time=time(9 + (i % 12), 0), calendar=CalendarType.SOLAR,
                        is_leap_month=False, gender=("female" if i % 2 else "male"),
                        apply_true_solar_time=False)
        out.append((bi, build_chart(bi)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--charts", type=int, default=3)
    ap.add_argument("--no-rag", action="store_true", help="RAG 생략(빠른 점검)")
    args = ap.parse_args()

    db = get_session_factory()()
    base_prompt = template_service.get_active_prompt(db)
    db.close()
    sys_content = cs._compose_sys_content(base_prompt, "standard", "normal")

    charts = _sample_charts(args.charts)
    total = init_ok = final_ok = 0
    fails = []
    for bi, ch in charts:
        cj = ch.model_dump(mode="json")
        summary = cs._build_saju_summary(ch, bi)
        truth = cs._myeongsik_truth(cj)
        for q in QUESTIONS:
            total += 1
            chunks = [] if args.no_rag else cs._retrieve_context(q, 6, "basic", session_id=None, question=q)
            user_prompt = cs._build_user_prompt(q, chunks, summary)
            msgs = [{"role": "system", "content": sys_content}, {"role": "user", "content": user_prompt}]
            try:
                draft = cs._call_ollama(msgs)
            except Exception as e:  # noqa: BLE001
                print(f"  [skip] 생성실패: {e}"); continue
            ib = cs._verify_myeongsik(draft, cj)
            if not ib:
                init_ok += 1
            fixed = cs._correct_chart(draft, cj, question=q, sys_content=sys_content, saju_summary=summary)
            fb = cs._verify_myeongsik(fixed, cj)
            if not fb:
                final_ok += 1
            else:
                fails.append((truth[:24], q, fb))
            mark = "OK " if not ib else ("→교정OK" if not fb else "✗미해결")
            print(f"  [{mark}] {truth[:30]} | {q[:14]} | init={ib or '일치'} final={fb or '일치'}")

    print("\n===== 명식 정합성 평가 =====")
    print(f"표본: {total}건 (명식 {len(charts)} × 질문 {len(QUESTIONS)})")
    print(f"init  일치율(예방): {init_ok}/{total} = {100*init_ok//max(1,total)}%")
    print(f"final 일치율(검증후): {final_ok}/{total} = {100*final_ok//max(1,total)}%  ← 목표 100%")
    if fails:
        print(f"미해결 {len(fails)}건:", fails[:5])
        return 1
    print("ALL_CONSISTENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
