# -*- coding: utf-8 -*-
"""궁합 PDF — 2인 명식 + 5요소 펜타곤 포함(운영자 지적 #12) + IDOR 소유검증.

- generate_consultation_pdf(compat=...) 가 두 명식 패널 + 펜타곤을 얹어 PDF를 키운다(하위호환 유지).
- _compat_data 는 회원 본인+비프리뷰만 반환 — compat_id 만 알면 남의 2인 명식을 뽑는 IDOR 차단.
"""
from __future__ import annotations

from datetime import date, time

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput
from backend.app.services.pdf_service import generate_consultation_pdf, _build_compat_pentagon


def _chart(y, m, d):
    c = build_chart(BirthInput(birth_date=date(y, m, d), birth_time=time(9, 30)))
    return c.model_dump(mode="json") if hasattr(c, "model_dump") else c


def _compat_payload():
    return {
        "a_chart": _chart(1990, 3, 15), "a_cap": "나 · 1990년 03월 15일 생 · 건명(乾命)",
        "b_chart": _chart(1992, 7, 20), "b_cap": "상대 · 1992년 07월 20일 생 · 곤명(坤命)",
        "factors": [("일지", 82), ("일간", 67), ("오행", 74), ("십성", 90), ("신살", 55)],
    }


def test_compat_pdf_adds_panels_and_is_valid():
    compat = _compat_payload()
    pdf = generate_consultation_pdf(doc_title="궁합 상담서", person_line="나 · 상대",
                                    item="궁합", content="종합 등급: 상.\n\n**일지**가 조화롭습니다.",
                                    compat=compat)
    base = generate_consultation_pdf(doc_title="궁합 상담서", person_line="나 · 상대",
                                     item="궁합", content="종합 등급: 상.\n\n**일지**가 조화롭습니다.")
    assert pdf[:5] == b"%PDF-" and base[:5] == b"%PDF-"
    assert len(pdf) > len(base), "2인 명식+펜타곤이 얹혀 PDF가 더 커야 함"


def test_pentagon_flowable_and_guards():
    d = _build_compat_pentagon(475, [("일지", 80), ("일간", 70), ("오행", 60), ("십성", 90), ("신살", 50)])
    assert d is not None and type(d).__name__ == "Drawing"
    # 축 부족·빈 입력은 None(패널 생략, PDF는 계속)
    assert _build_compat_pentagon(475, []) is None
    assert _build_compat_pentagon(475, [("일지", 80), ("일간", 70)]) is None
    # 점수 범위 밖(음수·>100)도 예외 없이 렌더(클램프)
    assert _build_compat_pentagon(475, [("a", -5), ("b", 150), ("c", 50), ("d", 0), ("e", 100)]) is not None


# ── IDOR: 회원 본인 + 비프리뷰만 ─────────────────────────────────
class _Row:
    def __init__(self, user_id, is_preview=False):
        self.user_id = user_id
        self.is_preview = is_preview
        self.created_at = None
        self.a_chart_json = {"pillars": {}}
        self.b_chart_json = {"pillars": {}}
        self.a_label = "홍길동테스트"; self.a_birth_date = date(1990, 1, 1); self.a_birth_time = None; self.a_gender = "male"
        self.b_label = "김영희테스트"; self.b_birth_date = date(1991, 1, 1); self.b_birth_time = None; self.b_gender = "female"
        self.f_day_branch = 80; self.f_day_stem = 70; self.f_wuxing = 60; self.f_ten_god = 90; self.f_sinsal = 50


class _DB:
    def __init__(self, row): self._row = row
    def get(self, model, key): return self._row


class _User:
    def __init__(self, uid): self.id = uid


def test_compat_data_owner_gets_panels():
    from backend.app.api.pdf import _compat_data
    c, _ = _compat_data(_DB(_Row(user_id=7)), "abc", _User(7))
    assert c is not None and len(c["factors"]) == 5 and c["a_chart"] is not None


def test_compat_caption_has_no_name():
    """명식 캡션에 이름/호칭이 새면 안 됨(개인정보 최소화 — 운영자 지적). 생년월일·건명/곤명만."""
    from backend.app.api.pdf import _compat_data
    c, _ = _compat_data(_DB(_Row(user_id=7)), "abc", _User(7))
    assert "테스트" not in c["a_cap"] and "테스트" not in c["b_cap"], "캡션에 이름 노출됨"
    assert "생 ·" in c["a_cap"] and ("건명" in c["a_cap"] or "곤명" in c["a_cap"])


def test_compat_data_idor_blocks_others():
    from backend.app.api.pdf import _compat_data
    row = _Row(user_id=7)
    assert _compat_data(_DB(row), "abc", _User(999))[0] is None, "타인 → 명식 차단(IDOR)"
    assert _compat_data(_DB(row), "abc", None)[0] is None, "비로그인 → 차단"
    # 미리보기(입장료 미결제)는 소유자여도 명식 생략
    assert _compat_data(_DB(_Row(user_id=7, is_preview=True)), "abc", _User(7))[0] is None
    # 세션 없음 → None
    assert _compat_data(_DB(None), "abc", _User(7))[0] is None
    # compat_id 없음 → None
    assert _compat_data(_DB(row), None, _User(7))[0] is None
