"""Phase 4A/4B/5B/5C/4C 통합 단위 테스트.

순수 함수 / 더미 모드 동작을 빠르게 검증. DB 미사용.
"""
from __future__ import annotations

import base64

import pytest


def test_payment_packages_loaded():
    from backend.app.core.config import get_settings
    s = get_settings()
    amounts = sorted(p["amount"] for p in s.payment_packages)
    # 충전 4종 + 연간회원 1종
    assert amounts == [10_000, 30_000, 50_000, 100_000, 120_000]
    # 모든 패키지 1P=1원 (연간회원도 12만원 → 120,000P)
    for p in s.payment_packages:
        assert p["amount"] == p["credits"], f"1P=1원 위반: {p}"
    # 연간회원: 120,000P 적립 + grade=annual
    annual = [p for p in s.payment_packages if p.get("grade") == "annual"]
    assert len(annual) == 1 and annual[0]["credits"] == 120_000


def test_is_dummy_key_detection():
    from backend.app.services.payment_service import _is_dummy_key
    assert _is_dummy_key("test_sk_DUMMY_REPLACE_ME") is True
    assert _is_dummy_key("") is True
    assert _is_dummy_key("test_sk_live_real1234") is False


def test_toss_basic_auth_format():
    """Toss confirm 호출의 Basic auth 헤더 인코딩 형식."""
    secret = "test_sk_live_abc"
    token = base64.b64encode(f"{secret}:".encode()).decode()
    assert ":" in base64.b64decode(token).decode()
    assert base64.b64decode(token).decode().endswith(":")


def test_oauth_dummy_detection():
    from backend.app.api.oauth import _is_dummy
    assert _is_dummy("DUMMY_KAKAO_CLIENT_ID")
    assert _is_dummy("")
    assert not _is_dummy("real_client_id_12345")


def test_oauth_provider_cfg_validation():
    from backend.app.api.oauth import _provider_cfg
    from fastapi import HTTPException

    for p in ("kakao", "google"):
        cfg = _provider_cfg(p)
        assert "authorize_url" in cfg
        assert "token_url" in cfg
        assert "userinfo_url" in cfg
        assert cfg["redirect_uri"]
    with pytest.raises(HTTPException):
        _provider_cfg("facebook")


def test_banner_valid_slots():
    from backend.app.services.admin_service import VALID_SLOTS
    assert VALID_SLOTS == {
        "top", "chat_top_1", "chat_top_2", "side_1", "side_2", "answer_bottom"
    }


def test_make_preview_abs_cut():
    """미리보기는 절대 문자수(preview_max_chars, 기본 220자) 기준으로 컷한다."""
    from backend.app.services.chat_service import _make_preview
    from backend.app.core.config import get_settings
    n = get_settings().preview_max_chars
    txt = "가나다라마바사아자차" * 40  # 400자 (>220)
    pv = _make_preview(txt)
    assert pv.endswith("...")
    # n자 컷 + " ..." 접미사 (rstrip로 최대 1자 감소 가능)
    assert n - 1 <= len(pv) - len(" ...") <= n


def test_make_preview_short_text_no_cut():
    from backend.app.services.chat_service import _make_preview
    pv = _make_preview("짧")
    assert pv == "짧"


def test_new_order_id_format():
    from backend.app.services.payment_service import _new_order_id
    import re
    oid = _new_order_id()
    assert re.match(r"^ord_\d{14}_[0-9a-f]{8}$", oid), f"unexpected: {oid}"
    # 두 번 호출 시 서로 다름
    assert _new_order_id() != oid
