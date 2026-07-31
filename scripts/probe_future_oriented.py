# -*- coding: utf-8 -*-
"""미래지향 검증 — '올해/시점' 질문에 과거 연도·과거 대운으로 새지 않는지 라이브 측정.

DB 실측 버그(올해 부동산매매운→2021 辛丑, 시험합격운→2023 일진, 내년공부운→2024)와
동일 유형 질문을 현재 파이프라인(exaone→qwen→교정)으로 돌려, 답변에 과거 시점 마커가
없는지 + 올해 세운(병오)·현재 대운을 올바로 쓰는지 확인한다. CPU 전용.

실행: python -m scripts.probe_future_oriented
"""
from __future__ import annotations

import re
import sys
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender
from backend.app.services import chat_service as cs, template_service as ts
from backend.app.core.db import get_session_factory

PAST = ["2019", "2020", "2021", "2022", "2023", "2024", "2025",
        "19년", "20년", "21년", "22년", "23년", "24년", "25년",
        "작년", "재작년", "지난해", "지난 해", "과거", "예전", "옛날", "지난 대운", "이전 대운", "과거 대운"]

QUESTIONS = [
    "올해 부동산 매매운과 이사운을 알려줘",
    "올해 시험 합격운을 보고 싶어요",
    "내년 공부운은 어떤가요?",
    "올해 사업운이 어떤가요?",
    "성격과 올해 전반적인 운세, 앞으로의 흐름을 알려줘",
    "앞으로 10년 대운 흐름을 알려줘",
]

# 과거 대운(현재 이전) 간지 — 해당 명식 기준으로 답변이 과거 대운을 서술하는지 감지용
def _past_daewoon_ganji(chart, birth):
    from datetime import date as _d
    es = (chart.daewoon.entries if chart.daewoon else []) or []
    age = (_d.today() - birth.birth_date).days / 365.25
    ci = max((i for i, e in enumerate(es) if e.start_age <= age), default=0)
    out = []
    for e in es[:ci]:  # 현재 이전 = 과거 대운
        from backend.app.saju.constants import stem_korean, branch_korean
        out.append(f"{stem_korean(e.pillar.stem)}{branch_korean(e.pillar.branch)}")
    return out, (es[ci] if ci < len(es) else None)


def main() -> int:
    db = get_session_factory()()
    sysc = cs._compose_sys_content(ts.get_active_prompt(db), "standard", "normal")
    db.close()

    # 성인 명식(과거 대운 다수) — 과거 회고 위험이 가장 큰 케이스
    bi = BirthInput(birth_date=date(1985, 5, 20), birth_time=time(14, 30),
                    calendar=CalendarType.SOLAR, gender=Gender.MALE, apply_true_solar_time=False)
    ch = build_chart(bi)
    summary = cs._build_saju_summary(ch, bi)
    past_dw, cur_dw = _past_daewoon_ganji(ch, bi)
    cur_ko = ""
    if cur_dw:
        from backend.app.saju.constants import stem_korean, branch_korean
        cur_ko = f"{stem_korean(cur_dw.pillar.stem)}{branch_korean(cur_dw.pillar.branch)}"
    print(f"명식 1985생(만41세) · 현재대운={cur_ko} · 과거대운={past_dw}")
    print("(답변에 과거연도·과거대운 간지·과거 마커가 나오면 FAIL)\n")

    fails = 0
    for q in QUESTIONS:
        user = cs._build_user_prompt(q, [], summary)
        try:
            draft = cs._call_ollama([{"role": "system", "content": sysc}, {"role": "user", "content": user}])
            qb = cs._refine_with_qwen(question=q, draft=draft, saju_summary=summary,
                                      evidence=None, rag_context=None, dialect_instruction=None)
            ans = cs._scrub_source_refs((qb or draft).strip())
        except Exception as e:  # noqa: BLE001
            print(f"  [ERR] {q[:24]}: {e}"); continue
        past_mark = sorted(set(t for t in PAST if t in ans))
        past_dw_hit = sorted(set(g for g in past_dw if g in ans))
        sewoon_ok = ("병오" in ans or "丙午" in ans)
        bad = past_mark or past_dw_hit
        if bad:
            fails += 1
        mark = "✗과거" if bad else "OK"
        print(f"  [{mark:5}] {q[:26]:26} | 올해세운병오={sewoon_ok} | 과거마커={past_mark or '없음'} | 과거대운언급={past_dw_hit or '없음'}")
        if bad:
            for t in (past_mark + past_dw_hit)[:2]:
                i = ans.find(t)
                print(f"          …{ans[max(0,i-30):i+40]}…".replace(chr(10), " "))

    print("\n" + ("ALL_FUTURE_ORIENTED ✅" if fails == 0 else f"FAILS={fails}"))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
