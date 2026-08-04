# -*- coding: utf-8 -*-
"""tool 메뉴 결정값 검증 — 택일 황도/손없음·개명 수리 4격 (전수감사 P1).

result_json의 실제 값과 답변 재서술을 대조. 날짜/격라벨 근접 앵커로 오탐 억제.
"""
from __future__ import annotations

from backend.app.services.tool_service import _verify_gaemyeong_suri, _verify_taekil

TAEKIL_RJ = {
    "best": [{"date": "2026-07-15", "ganzhi": "병오", "hwangdo": "청룡(황도)", "sonless": True, "score": 88, "grade": "길"}],
    "avoid": [{"date": "2026-07-20", "ganzhi": "신해", "hwangdo": "천뢰(흑도)", "sonless": False, "score": 40, "grade": "흉"}],
}


def test_taekil_hwangdo_flip_flagged():
    # 15일은 황도인데 흑도로 재서술
    bad = _verify_taekil("2026-07-15은 흑도라 피하는 게 좋습니다.", TAEKIL_RJ)
    assert len(bad) == 1 and "황도" in bad[0][2]


def test_taekil_sonless_flip_flagged():
    bad = _verify_taekil("2026-07-15은 손있는 날입니다.", TAEKIL_RJ)
    assert len(bad) == 1


def test_taekil_correct_passes():
    ok = "2026-07-15은 청룡 황도에 손없는 날이라 길합니다. 2026-07-20은 흑도라 피하세요."
    assert _verify_taekil(ok, TAEKIL_RJ) == []


def test_taekil_unlisted_date_ignored():
    # result_json에 없는 날짜는 검사 안 함(오탐 방지)
    assert _verify_taekil("2026-08-01은 흑도입니다.", TAEKIL_RJ) == []


# ⚠️ 라벨은 실엔진(naming._four_pillars)과 동일한 '원격(元)' 형태여야 한다 — 종전 픽스처가
# 맨 라벨('원격')이라 검증기의 라벨 불일치 버그(항상 None 조회 → no-op)를 못 잡았다(false-green).
GAEM_RJ = {
    "kind": "gaemyeong",
    "analysis": {"four_pillars": {
        "won": {"label": "원격(元)", "num": 22, "grade": "흉"},
        "hyeong": {"label": "형격(亨)", "num": 15, "grade": "길"},
        "i": {"label": "이격(利)", "num": 25, "grade": "길"},
        "jeong": {"label": "정격(貞)", "num": 37, "grade": "길"},
    }},
}


def test_suri_wrong_num_flagged():
    bad = _verify_gaemyeong_suri("원격은 20획으로 흉합니다.", GAEM_RJ)
    assert len(bad) == 1 and "22획" in bad[0][2]


def test_suri_correct_passes():
    assert _verify_gaemyeong_suri("원격 22획(흉), 형격 15획(길), 정격 37획입니다.", GAEM_RJ) == []


def test_suri_real_engine_labels():
    """실엔진 four_pillars 산출물 그대로에서도 검증기가 동작(죽은 코드 회귀 방지)."""
    from backend.app.saju import naming as N
    rj = {"kind": "gaemyeong", "analysis": {"four_pillars": N._four_pillars("金", "民秀")}}
    won = rj["analysis"]["four_pillars"]["won"]["num"]
    assert _verify_gaemyeong_suri(f"원격 {won + 7}획으로 봅니다.", rj), "실엔진 라벨에서 미검출(죽은 코드)"
    assert _verify_gaemyeong_suri(f"원격 {won}획입니다.", rj) == []


def test_suri_only_gaemyeong():
    # 작명(kind!=gaemyeong)엔 four_pillars 미주입 → 미적용
    assert _verify_gaemyeong_suri("원격 20획", {"kind": "jakmyeong"}) == []
