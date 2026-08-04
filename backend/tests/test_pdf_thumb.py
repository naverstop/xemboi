# -*- coding: utf-8 -*-
"""공유 카드용 PDF 첫장 썸네일(thumb.png) — 운영자 지적 #9 '카카오 공유에 안내 이미지만 온다'.

데스크톱 카카오 웹은 파일첨부가 원천 불가라 링크 카드가 상한. 카드 대표이미지를 앱 아이콘 대신
'실제 상담서 첫 장'으로 바꿔 문서처럼 보이게 한다(모바일은 navigator.share 로 PDF 파일 자체 전송).
"""
from __future__ import annotations

import fitz  # PyMuPDF

from backend.app.api import pdf as P


def _make_pdf(token: str) -> None:
    P._PDF_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((72, 72), "상담서 첫 장 테스트", fontsize=18)
    (P._PDF_DIR / f"{token}.pdf").write_bytes(doc.tobytes())
    doc.close()


def test_thumb_renders_png_and_caches():
    tok = "aa11bb22" * 4  # 32 hex
    _make_pdf(tok)
    thumb = P._PDF_DIR / f"{tok}.thumb.png"
    try:
        resp = P.get_pdf_thumb(tok)
        assert resp.media_type == "image/png"
        assert thumb.is_file(), "썸네일 파일이 생성돼야 함"
        assert thumb.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "PNG 시그니처"
        # 2차 호출은 캐시 재사용(재래스터화 없이 동일 파일)
        mtime1 = thumb.stat().st_mtime_ns
        P.get_pdf_thumb(tok)
        assert thumb.stat().st_mtime_ns == mtime1, "캐시된 썸네일 재사용(재생성 금지)"
    finally:
        (P._PDF_DIR / f"{tok}.pdf").unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)


def test_thumb_404_for_missing_and_bad_token():
    from fastapi import HTTPException
    for bad in ("nope", "../etc", "zz"):
        try:
            P.get_pdf_thumb(bad)
            assert False, f"{bad!r} 는 404 여야 함"
        except HTTPException as e:
            assert e.status_code == 404
    # 형식은 맞지만 없는 토큰
    try:
        P.get_pdf_thumb("c0ffee00" * 4)
        assert False, "없는 토큰은 404"
    except HTTPException as e:
        assert e.status_code == 404


def test_purge_removes_thumb_sidecar():
    """TTL 스윕이 .thumb.png 사이드카도 함께 지우는지(고아 캐시 방지)."""
    import os
    tok = "dd33ee44" * 4
    _make_pdf(tok)
    thumb = P._PDF_DIR / f"{tok}.thumb.png"
    P.get_pdf_thumb(tok)
    assert thumb.is_file()
    pdf_path = P._PDF_DIR / f"{tok}.pdf"
    old = os.stat(pdf_path).st_mtime - 999 * 86400   # 아주 오래된 것으로
    os.utime(pdf_path, (old, old))
    try:
        P.purge_expired_pdfs(ttl_days=1)
        assert not pdf_path.is_file(), "만료 PDF 삭제"
        assert not thumb.is_file(), "썸네일 사이드카도 함께 삭제"
    finally:
        pdf_path.unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)
