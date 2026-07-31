# -*- coding: utf-8 -*-
"""명식 정합성 검증 회귀 테스트 — LLM 불필요(빠름).

chat_service._verify_myeongsik 가 ① 답변의 틀린 4주 지지를 정확히 검출하고
② 정상답변·개념(봄 寅卯辰)·대운(병인) 언급은 오탐하지 않는지 고정 케이스로 검증.
'사주 명식과 답변 지지 불일치' 버그(2026-06-16)의 재발 방지용.

실행: python -m scripts.test_myeongsik_fidelity   (실패 시 비0 종료)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services import chat_service as cs

# 기준 명식: 년巳 월子 일戌 시午 (은정 명식)
CHART = {"pillars": {
    "year": {"stem": "癸", "branch": "巳"},
    "month": {"stem": "甲", "branch": "子"},
    "day": {"stem": "甲", "branch": "戌"},
    "hour": {"stem": "庚", "branch": "午"},
}}

CASES = [
    # (이름, 답변, 불일치_검출되어야_함)
    ("버그답변", "사주명식 요약\n월지: 인목(寅木)\n일지: 유금(酉金)\n년지: 해자(亥子)", True),
    ("정상답변", "월지 자수(子水), 일지 술토(戌土), 년지 사화(巳火)로 구성됩니다.", False),
    ("개념언급", "봄철(寅卯辰)과 여름(巳午未)의 조후를 봅니다.", False),
    ("대운언급", "30대 대운 병인(丙寅), 40대 정묘(丁卯). 월지 자수(子水)와 조화.", False),
    ("부분오류", "월지 자수(子水)는 좋으나 일지 유금(酉金)이 약점.", True),
    ("지지미언급", "일간 갑목으로 창의적이며 리더십이 있습니다.", False),
]


def main() -> int:
    fails = []
    for name, ans, should_flag in CASES:
        flagged = bool(cs._verify_myeongsik(ans, CHART))
        ok = flagged == should_flag
        print(f"[{'OK' if ok else 'FAIL'}] {name}: flag={flagged} (기대={should_flag})")
        if not ok:
            fails.append(name)
    # 기준값/교정문 sanity
    assert cs._pillar_branches(CHART) == {"year": "巳", "month": "子", "day": "戌", "hour": "午"}
    assert "월지=자(子)" in cs._myeongsik_truth(CHART)
    if fails:
        print(f"\nFAILED: {fails}")
        return 1
    print("\nALL_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
