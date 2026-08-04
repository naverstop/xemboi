"""입점 신청·승인 + 월 정산주기(운영자 확정 2026-07-11)."""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
from backend.app.repositories import auth_models  # noqa: F401
from backend.app.repositories.consultation_models import Consultant, ConsultantApplication
from backend.app.services import consultation_service as svc
from backend.app.services.settlement_cycle import cycle_of, cycle_window, payout_date


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close(); engine.dispose()


def _user(email="applicant@test.internal", uid=10):
    return SimpleNamespace(id=uid, email=email)


def test_apply_and_approve_grants_consultant(db):
    a = svc.create_application(db, _user(), specialty="both", business_name="달빛상담소",
                               contact="010-0000-0000", intro="경력 10년", ip="1.2.3.4")
    assert a.status == "pending"
    assert a.terms_version and a.terms_sha256 and len(a.terms_text) > 500   # 동의 전문 스냅샷 보존
    # 중복 신청 차단
    with pytest.raises(ValueError):
        svc.create_application(db, _user(), specialty="saju", business_name="중복")
    # 승인 → consultants 생성 + login_email 매핑
    out = svc.approve_application(db, a.id)
    assert out["status"] == "approved" and out["consultant_id"]
    c = db.get(Consultant, out["consultant_id"])
    assert c.login_email == "applicant@test.internal" and c.specialty == "both"
    # 이미 입점이면 재신청 차단
    with pytest.raises(ValueError):
        svc.create_application(db, _user(), specialty="saju", business_name="재신청")


def test_reject_records_reason(db):
    a = svc.create_application(db, _user("rej@test.internal", 11), specialty="tarot", business_name="반려테스트")
    out = svc.reject_application(db, a.id, reason="서류 미비")
    assert out["status"] == "rejected" and out["reject_reason"] == "서류 미비"
    # 반려 후 재신청 가능
    a2 = svc.create_application(db, _user("rej@test.internal", 11), specialty="tarot", business_name="재도전")
    assert a2.status == "pending"


def test_apply_docs_saved_and_validated(db, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_PARTNER_DOCS_DIR", tmp_path)
    a = svc.create_application(
        db, _user("docs@test.internal", 12), specialty="saju", business_name="서류상담소",
        docs=[("biz_license", "사업자등록증.pdf", b"%PDF-1.4 fake"),
              ("bank_book", "통장사본.jpg", b"\xff\xd8 fake"),
              ("evidence", "입점증빙.png", b"\x89PNG fake")],
    )
    docs = svc.json.loads(a.docs_json)
    assert [d["kind"] for d in docs] == ["biz_license", "bank_book", "evidence"]
    assert all(len(d["id"]) == 32 for d in docs)               # uuid 파일명(경로순회 방지)
    # 열람 경로 검증 — docs_json 경유만 허용
    p, name = svc.application_doc_path(a, docs[0]["id"])
    assert p.exists() and name == "사업자등록증.pdf"
    with pytest.raises(LookupError):
        svc.application_doc_path(a, "no-such-doc")
    # 확장자 화이트리스트·크기 상한
    with pytest.raises(ValueError):
        svc.save_application_docs(a.id, [("evidence", "악성.exe", b"MZ")])
    with pytest.raises(ValueError):
        svc.save_application_docs(a.id, [("evidence", "큰파일.png", b"0" * (10 * 1024 * 1024 + 1))])
    # dict 직렬화 시 path 비노출(관리자 API 경유 열람)
    d = svc.application_dict(a)
    assert d["docs"] and all("path" not in x for x in d["docs"])


def test_apply_docs_no_orphan_on_partial_failure(tmp_path, monkeypatch):
    """후속 파일 검증 실패 시 앞선 파일(통장사본 PII)이 디스크에 남으면 안 됨 — 선검증 후 일괄 기록."""
    monkeypatch.setattr(svc, "_PARTNER_DOCS_DIR", tmp_path)
    with pytest.raises(svc.DocValidationError):
        svc.save_application_docs(99, [("biz_license", "정상.pdf", b"%PDF ok"),
                                       ("bank_book", "통장.jpg", b"\xff\xd8 ok"),
                                       ("evidence", "위반.txt", b"bad")])
    assert not (tmp_path / "99").exists()   # 검증 단계 실패 → 아무것도 기록되지 않음


def test_inquiry_gate_lifecycle(db):
    """운영자 확정 프로세스: 문의 → 관리자 허용 → 신청 자격. 허용 전 can_apply=False."""
    u = _user("gate@test.internal", 13)
    assert svc.can_apply(db, u) is False
    q = svc.create_inquiry(db, u, note="경력 10년")
    assert q.status == "pending" and svc.can_apply(db, u) is False   # 접수만으론 자격 없음
    with pytest.raises(ValueError):                                   # 중복 문의 차단
        svc.create_inquiry(db, u)
    out = svc.allow_inquiry(db, q.id)
    assert out["status"] == "allowed" and svc.can_apply(db, u) is True
    with pytest.raises(ValueError):                                   # 허용 후 재문의도 차단
        svc.create_inquiry(db, u)
    # 신청→반려 후에도 재신청 자격 유지(신청 이력 기반)
    a = svc.create_application(db, u, specialty="saju", business_name="게이트상담소")
    svc.reject_application(db, a.id, reason="테스트")
    assert svc.can_apply(db, u) is True


def test_inquiry_dismiss_and_retry(db):
    u = _user("gate2@test.internal", 14)
    q = svc.create_inquiry(db, u)
    out = svc.dismiss_inquiry(db, q.id, reason="정보 부족")
    assert out["status"] == "dismissed" and out["decide_note"] == "정보 부족"
    assert svc.can_apply(db, u) is False
    q2 = svc.create_inquiry(db, u, note="보완했습니다")   # 기각 후 재문의 가능
    assert q2.status == "pending" and q2.id != q.id
    assert svc.my_inquiry(db, u).id == q2.id             # 진행 중 문의 우선 반환


def test_settlement_cycle_rules():
    # 25일 24시 마감: 25일 23:59는 당월, 26일 00:00은 익월
    assert cycle_of(datetime(2026, 7, 25, 23, 59)) == "2026-07"
    assert cycle_of(datetime(2026, 7, 26, 0, 0)) == "2026-08"
    assert cycle_of(datetime(2026, 12, 27)) == "2027-01"      # 연 경계
    w0, w1 = cycle_window("2026-08")
    assert w0 == datetime(2026, 7, 26) and w1 == datetime(2026, 8, 26)
    # 지급일 = 당월 마지막 영업일
    assert payout_date("2026-07") == date(2026, 7, 31)         # 금
    assert payout_date("2026-10") == date(2026, 10, 30)        # 10/31 토 → 10/30 금
    assert payout_date("2027-01") == date(2027, 1, 29)         # 1/31 일 → 1/29 금
    assert payout_date("2027-12") == date(2027, 12, 31)        # 금(성탄 대체 12/27과 무관)
