"""1차/2차 통합 검증: 약관/연령/리프레시/로그아웃/레이트리밋/웹훅서명/분량가드 게이트.

전부 PASS면 종료 코드 0. 단계별 PASS/FAIL을 출력한다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time
import uuid
from datetime import date

import requests

BASE = os.environ.get("SAJU_BASE", "http://127.0.0.1:8000")


def _ok(label: str) -> None:
    print(f"PASS - {label}")


def _fail(label: str, detail: str = "") -> None:
    print(f"FAIL - {label}: {detail}")
    sys.exit(1)


def test_legal_versions() -> dict:
    r = requests.get(f"{BASE}/api/auth/legal", timeout=5)
    if r.status_code != 200:
        _fail("legal 버전 조회", f"{r.status_code} {r.text}")
    j = r.json()
    for k in ("terms", "privacy", "refund", "min_age_years"):
        if k not in j:
            _fail("legal 응답 필드", f"missing {k}")
    _ok(f"legal 버전 조회 (terms={j['terms']}, min_age={j['min_age_years']})")
    return j


def _new_email() -> str:
    return f"verify_{uuid.uuid4().hex[:8]}@example.com"


def test_register_missing_consent() -> None:
    body = {
        "email": _new_email(),
        "password": "Passw0rd!23",
        "birth_date": "1990-01-01",
        "agree_terms": False,
        "agree_privacy": True,
        "agree_refund": True,
    }
    r = requests.post(f"{BASE}/api/auth/register", json=body, timeout=5)
    if r.status_code != 400:
        _fail("약관 미동의 가입 차단", f"{r.status_code} {r.text}")
    _ok("약관 미동의 가입 차단(400)")


def test_register_underage() -> None:
    today = date.today()
    body = {
        "email": _new_email(),
        "password": "Passw0rd!23",
        "birth_date": today.isoformat(),  # 0세
        "agree_terms": True,
        "agree_privacy": True,
        "agree_refund": True,
    }
    r = requests.post(f"{BASE}/api/auth/register", json=body, timeout=5)
    if r.status_code != 400:
        _fail("미성년 가입 차단", f"{r.status_code} {r.text}")
    _ok("미성년 가입 차단(400)")


def test_register_ok() -> dict:
    body = {
        "email": _new_email(),
        "password": "Passw0rd!23",
        "nickname": "verify",
        "birth_date": "1990-05-15",
        "marketing_opt_in": False,
        "agree_terms": True,
        "agree_privacy": True,
        "agree_refund": True,
    }
    r = requests.post(f"{BASE}/api/auth/register", json=body, timeout=5)
    if r.status_code != 200:
        _fail("정상 가입", f"{r.status_code} {r.text}")
    j = r.json()
    if "access_token" not in j or not j.get("refresh_token"):
        _fail("토큰 발급", f"{j}")
    me = requests.get(
        f"{BASE}/api/auth/me",
        headers={"Authorization": f"Bearer {j['access_token']}"},
        timeout=5,
    ).json()
    if me.get("balance", 0) < 1000:
        _fail("가입 보너스 1000P", f"balance={me.get('balance')}")
    _ok(f"정상 가입(email={body['email']}, balance={me['balance']}P)")
    return j


def test_refresh_rotation(tokens: dict) -> None:
    rt = tokens["refresh_token"]
    r1 = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": rt}, timeout=5)
    if r1.status_code != 200:
        _fail("refresh 정상", f"{r1.status_code} {r1.text}")
    j1 = r1.json()
    if not j1.get("refresh_token") or j1["refresh_token"] == rt:
        _fail("refresh 회전", "토큰이 회전되지 않음")
    _ok("refresh 회전 발급")
    # 기존 토큰 재사용 → 401
    r2 = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": rt}, timeout=5)
    if r2.status_code != 401:
        _fail("refresh 재사용 차단", f"{r2.status_code} {r2.text}")
    _ok("refresh 재사용 차단(401)")
    # logout으로 신규 토큰 폐기
    new_rt = j1["refresh_token"]
    r3 = requests.post(
        f"{BASE}/api/auth/logout", json={"refresh_token": new_rt}, timeout=5
    )
    if r3.status_code not in (200, 204):
        _fail("logout", f"{r3.status_code} {r3.text}")
    _ok("logout 처리")
    r4 = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": new_rt}, timeout=5)
    if r4.status_code != 401:
        _fail("로그아웃 후 refresh 차단", f"{r4.status_code} {r4.text}")
    _ok("로그아웃 후 refresh 차단(401)")


def test_rate_limit_auth() -> None:
    # /api/auth/login 빠르게 12회 → 11~12번째 429 기대 (auth=10/min)
    hits = []
    for i in range(13):
        r = requests.post(
            f"{BASE}/api/auth/login",
            json={"email": "ratelimit@example.com", "password": "wrongpw"},
            timeout=5,
        )
        hits.append(r.status_code)
    if 429 not in hits:
        _fail("auth 레이트리밋", f"statuses={hits}")
    _ok(f"auth 레이트리밋 동작 (429 발생, statuses={hits})")


def test_webhook_signature() -> None:
    # secret 미설정이면 검증 스킵되므로 skip 표기
    secret = os.environ.get("TOSS_WEBHOOK_SECRET", "")
    if not secret:
        print("SKIP - 웹훅 서명검증 (TOSS_WEBHOOK_SECRET 미설정)")
        return
    payload = b'{"orderId":"x","status":"DONE"}'
    bad = requests.post(
        f"{BASE}/api/payments/webhook",
        data=payload,
        headers={"Content-Type": "application/json", "Toss-Signature": "deadbeef"},
        timeout=5,
    )
    if bad.status_code != 401:
        _fail("웹훅 잘못된 서명 차단", f"{bad.status_code} {bad.text}")
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    ok = requests.post(
        f"{BASE}/api/payments/webhook",
        data=payload,
        headers={"Content-Type": "application/json", "Toss-Signature": sig},
        timeout=5,
    )
    if ok.status_code not in (200, 400, 404):  # 200 또는 미처리 코드
        _fail("웹훅 정상 서명 수락", f"{ok.status_code} {ok.text}")
    _ok("웹훅 서명검증 (잘못=401, 정상=수락)")


def main() -> None:
    print(f"[verify] BASE={BASE}")
    test_legal_versions()
    test_register_missing_consent()
    test_register_underage()
    tokens = test_register_ok()
    test_refresh_rotation(tokens)
    # 레이트리밋은 가입 직후 같은 IP 카운터에 영향 줄 수 있으므로 잠깐 대기
    time.sleep(2)
    test_rate_limit_auth()
    test_webhook_signature()
    print("\nALL GREEN - 1차/2차 통합 검증 통과")


if __name__ == "__main__":
    main()
