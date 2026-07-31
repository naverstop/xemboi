"""AES-256-GCM 기반 PII 암복호 헬퍼.

키는 settings.pii_aes_key_b64 (32바이트 url-safe base64). 비어있으면 암호화 비활성화 모드.
포맷: base64(nonce_12 || ciphertext_with_tag) — URL-safe.
"""
from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.core.config import get_settings


def _key() -> Optional[bytes]:
    raw = (get_settings().pii_aes_key_b64 or "").strip()
    if not raw:
        return None
    try:
        k = base64.urlsafe_b64decode(raw + "==")
    except Exception:
        return None
    if len(k) != 32:
        return None
    return k


def is_enabled() -> bool:
    return _key() is not None


def encrypt_str(plain: Optional[str]) -> Optional[str]:
    if plain is None:
        return None
    k = _key()
    if k is None:
        return None
    nonce = os.urandom(12)
    ct = AESGCM(k).encrypt(nonce, plain.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii").rstrip("=")


def decrypt_str(blob: Optional[str]) -> Optional[str]:
    if blob is None:
        return None
    k = _key()
    if k is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(blob + "==")
        nonce, ct = raw[:12], raw[12:]
        pt = AESGCM(k).decrypt(nonce, ct, None)
        return pt.decode("utf-8")
    except Exception:
        return None
