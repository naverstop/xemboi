"""컬럼 레벨 투명 암호화 타입(SQLAlchemy TypeDecorator) — 저장 시 암호화, 조회 시 복호화.

애플리케이션 코드는 평문(date/str/float)만 다루고, DB에는 AES-256-GCM 암호문(Text)만 저장된다(M2/②).
저장소는 Text(암호문). 해당 컬럼으로 SQL 필터·정렬은 불가(암호문) — saju_profiles 는 birth 로 조회하지 않음(확인됨).
"""
from __future__ import annotations

import logging
from datetime import date as _date

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from backend.app.core.crypto import decrypt_str, encrypt_str

_log = logging.getLogger("saju.crypto")


def _decrypt_or_warn(value):
    """복호 시도 — 암호문이 있는데 복호가 None(키 부재/손상)이면 경고 로그로 표면화(D6, 무음 PII 손실 방지)."""
    out = decrypt_str(value)
    if out is None and value is not None:
        _log.error("PII 복호 실패 — 키(PII_AES_KEY_B64) 회전/손상 의심. 무음 손실 방지 위해 경보. (값 앞자리 %s…)", str(value)[:8])
    return out


class EncryptedString(TypeDecorator):
    """문자열(또는 JSON 문자열) 투명 암호화."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # 저장(평문→암호문)
        if value is None:
            return None
        return encrypt_str(str(value))

    def process_result_value(self, value, dialect):  # 조회(암호문→평문)
        if value is None:
            return None
        return _decrypt_or_warn(value)


class EncryptedDate(TypeDecorator):
    """date 투명 암호화 — ISO 문자열로 암호화 저장, 조회 시 date 복원."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        iso = value.isoformat() if hasattr(value, "isoformat") else str(value)
        return encrypt_str(iso)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        dec = _decrypt_or_warn(value)
        return _date.fromisoformat(dec) if dec else None


class EncryptedFloat(TypeDecorator):
    """float 투명 암호화 — 문자열로 암호화 저장, 조회 시 float 복원."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_str(repr(float(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        dec = _decrypt_or_warn(value)
        return float(dec) if dec else None
