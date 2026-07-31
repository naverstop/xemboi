"""ZIP 일괄 업로드(ingest_zip) 테스트.

전문가에게 받은 zip 을 그대로 올리면 서버가 풀어 pdf/이미지/txt 를 기존 업로드
파이프라인(submit_upload + approve_and_index)에 투입한다. 색인(OCR/임베딩)은
이후 학습 배치가 수행하므로 본 테스트는 '추출·적재·분류'까지만 검증한다.

DB 는 인메모리 SQLite, 파일 경로(PROJECT_ROOT/inbox/learn_new/approved)는 tmp 로 패치.
"""
from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
import backend.app.repositories.upload_models  # noqa: F401  (uploads 테이블 등록)
from backend.app.services import upload_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def tmp_dirs(tmp_path, monkeypatch):
    # PROJECT_ROOT 및 적재 경로를 tmp 로 — relative_to(PROJECT_ROOT) 성립 + 실제 프로젝트 폴더 오염 방지
    monkeypatch.setattr(upload_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(upload_service, "INBOX_DIR", tmp_path / "inbox")
    monkeypatch.setattr(upload_service, "LEARN_NEW_DIR", tmp_path / "learn_new")
    monkeypatch.setattr(upload_service, "APPROVED_DIR", tmp_path / "approved")
    return tmp_path


def _make_zip() -> bytes:
    long_txt = "이것은 충분히 긴 학습용 텍스트입니다. 명리 강의 노트 발췌. " * 3  # >=30자
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes/lecture.txt", long_txt)                 # extracted (txt)
        z.writestr("scan.pdf", b"%PDF-1.4 fake pdf bytes")        # extracted (pdf, 복사만)
        z.writestr("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64) # extracted (image, 복사만)
        z.writestr("memo.docx", b"unsupported binary")            # skipped (미지원 확장자)
        z.writestr("dup.txt", long_txt)                           # duplicate (lecture.txt 와 동일 sha)
        z.writestr("tiny.txt", "짧음")                            # rejected (추출 텍스트 너무 짧음)
    return buf.getvalue()


def test_ingest_zip_classifies_and_stages(db, tmp_dirs):
    summary = upload_service.ingest_zip(db, content=_make_zip(), submitter="admin@test")

    assert summary["total_in_zip"] == 6
    assert set(summary["extracted"]) == {"lecture.txt", "scan.pdf", "photo.png"}
    assert summary["duplicates"] == ["dup.txt"]
    assert summary["skipped"] == ["memo.docx"]
    assert summary["rejected"] == ["tiny.txt"]

    # pdf/이미지는 학습자료_new 로 복사(배치 OCR 대상), txt 는 추출본으로 적재
    learn_new = list((tmp_dirs / "learn_new").glob("*"))
    assert sorted(p.suffix.lower() for p in learn_new) == [".pdf", ".png"]
    approved = list((tmp_dirs / "approved").glob("*.txt"))
    assert len(approved) == 1  # lecture.txt 추출본


def test_ingest_zip_rejects_non_zip(db, tmp_dirs):
    with pytest.raises(ValueError):
        upload_service.ingest_zip(db, content=b"not a zip at all", submitter="admin@test")


def test_zip_member_name_sanitizes_path_traversal():
    # zip-slip: 경로가 들어와도 basename 만 사용
    info = zipfile.ZipInfo(filename="../../etc/evil.pdf")
    info.flag_bits |= 0x800  # UTF-8 파일명(인코딩 보정 건너뜀)
    assert upload_service._zip_member_name(info) == "evil.pdf"
