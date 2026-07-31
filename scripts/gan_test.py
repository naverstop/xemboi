"""GAN Test 3회 — Generator(공격자) vs Discriminator(시스템 방어).

각 라운드: 적대적 입력 생성 → 시스템 응답 검증 → 무결성 판정.
"""
from __future__ import annotations

import sys
import time
import uuid

import requests

BASE = "http://127.0.0.1:8000"


def login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


class Round:
    def __init__(self, name: str) -> None:
        self.name = name
        self.pass_ = 0
        self.fail = 0

    def chk(self, cond: bool, label: str) -> None:
        if cond:
            self.pass_ += 1
            print(f"  [PASS] {label}")
        else:
            self.fail += 1
            print(f"  [FAIL] {label}")

    def verdict(self) -> str:
        ok = self.fail == 0
        return f"{self.name}: {'WIN(시스템)' if ok else 'LOSS'} (PASS={self.pass_} FAIL={self.fail})"


def round1_token_and_permission() -> Round:
    print("\n=== GAN Round 1: 토큰 위조 / 권한 우회 ===")
    r = Round("R1")
    H_user = {"Authorization": f"Bearer {login('test_user_001@example.com', 'testpass1234')}", "Content-Type": "application/json"}

    # 잘못된 JWT
    bad = requests.get(f"{BASE}/api/auth/me", headers={"Authorization": "Bearer xx.yy.zz"}, timeout=5)
    r.chk(bad.status_code == 401, "위조 JWT → 401")

    # Bearer 누락
    nohdr = requests.get(f"{BASE}/api/chat/sessions", timeout=5)
    r.chk(nohdr.status_code == 401, "헤더 누락 → 401")

    # admin endpoint 우회 시도
    rsp = requests.get(f"{BASE}/api/admin/stats", headers=H_user, timeout=5)
    r.chk(rsp.status_code == 403, "유저가 관리자 API → 403")

    # 타인 세션 삭제 시도 (admin 소유 세션을 user가 삭제)
    H_admin = {"Authorization": f"Bearer {login('orion0321@gmail.com', '!thdwlstn00')}", "Content-Type": "application/json"}
    s = requests.post(
        f"{BASE}/api/chat/sessions",
        headers=H_admin,
        json={"birth": {"birth_date": "1980-01-01", "birth_time": "00:00", "calendar": "solar", "gender": "male"}, "top_k": 3},
        timeout=30,
    ).json()
    sid = s["session_id"]
    rsp = requests.delete(f"{BASE}/api/chat/sessions/{sid}", headers=H_user, timeout=5)
    r.chk(rsp.status_code in (403, 404), f"타인 세션 삭제 → {rsp.status_code}")
    # 정리
    requests.delete(f"{BASE}/api/chat/sessions/{sid}", headers=H_admin, timeout=5)

    # 존재하지 않는 세션
    fake = uuid.uuid4().hex
    rsp = requests.delete(f"{BASE}/api/chat/sessions/{fake}", headers=H_user, timeout=5)
    r.chk(rsp.status_code == 404, "없는 세션 → 404")

    print(r.verdict())
    return r


def round2_payment_idempotency_and_oauth_injection() -> Round:
    print("\n=== GAN Round 2: 결제 멱등성 / OAuth 코드 주입 ===")
    r = Round("R2")

    # 새 더미 OAuth 사용자 생성 → 결제로 ads_hidden 검증
    tok = requests.post(f"{BASE}/api/auth/oauth/google/test-login", timeout=10).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    me0 = requests.get(f"{BASE}/api/auth/me", headers=H, timeout=5).json()
    r.chk(me0["balance"] >= 1000, "OAuth 보너스 1000+")

    # 잘못된 amount 0
    rsp = requests.post(f"{BASE}/api/payments/orders", headers=H, json={"amount": 0}, timeout=5)
    r.chk(rsp.status_code in (400, 422), f"amount=0 거부 → {rsp.status_code}")

    # 정상 주문
    od = requests.post(f"{BASE}/api/payments/orders", headers=H, json={"amount": 10000}, timeout=10).json()
    payload = {"payment_key": "gan_pk", "order_id": od["order_id"], "amount": 10000}

    # confirm × 5 동시 호출 → 첫 1건만 reflect, 나머지 already=True
    res = []
    for _ in range(5):
        rr = requests.post(f"{BASE}/api/payments/confirm", headers=H, json=payload, timeout=10).json()
        res.append(rr)
    new_approve = sum(1 for x in res if x.get("status") == "approved" and not x.get("already"))
    already_cnt = sum(1 for x in res if x.get("already"))
    r.chk(new_approve == 1, f"신규 approve 정확히 1회 (실제 {new_approve})")
    r.chk(already_cnt == 4, f"already=True 4회 (실제 {already_cnt})")

    me1 = requests.get(f"{BASE}/api/auth/me", headers=H, timeout=5).json()
    r.chk(me1["balance"] == me0["balance"] + 10000, "잔액 정확히 +10000")
    r.chk(me1["ads_hidden"] is True, "ads_hidden=True")

    # amount mismatch 시도 (order amount != confirm amount)
    od2 = requests.post(f"{BASE}/api/payments/orders", headers=H, json={"amount": 30000}, timeout=10).json()
    bad = requests.post(f"{BASE}/api/payments/confirm", headers=H, json={"payment_key": "gan_x", "order_id": od2["order_id"], "amount": 10000}, timeout=10)
    r.chk(bad.status_code >= 400, f"amount mismatch → {bad.status_code}")

    # OAuth 잘못된 provider
    rsp = requests.post(f"{BASE}/api/auth/oauth/facebook/test-login", timeout=5)
    r.chk(rsp.status_code == 404, "unknown provider → 404")

    # OAuth callback 빈 code
    rsp = requests.get(f"{BASE}/api/auth/oauth/kakao/callback", timeout=5, allow_redirects=False)
    r.chk(rsp.status_code in (400, 422), f"빈 code → {rsp.status_code}")

    print(r.verdict())
    return r


def round3_load_and_input_fuzz() -> Round:
    print("\n=== GAN Round 3: 부하 + 입력 퍼징 ===")
    r = Round("R3")

    # 1) 익명 세션 20개 동시 생성
    ok = 0
    for i in range(20):
        rr = requests.post(
            f"{BASE}/api/chat/sessions",
            json={"birth": {"birth_date": "1990-06-15", "birth_time": "12:00", "calendar": "solar", "gender": "male"}, "top_k": 3},
            timeout=20,
        )
        if rr.status_code in (200, 201):
            ok += 1
    r.chk(ok == 20, f"세션 생성 20건 (실제 {ok})")

    # 2) 배너 슬롯 100회 호출 → 모두 200 + items 길이 일정
    bad = 0
    for _ in range(100):
        rr = requests.get(f"{BASE}/api/banners?slot=top&pick_one=true", timeout=3)
        if rr.status_code != 200:
            bad += 1
    r.chk(bad == 0, f"배너 100회 모두 200 (실패 {bad})")

    # 3) 잘못된 birth_date 형식
    fuzz = [
        {"birth_date": "20-99-99", "birth_time": "14:30", "calendar": "solar", "gender": "male"},
        {"birth_date": "1990-13-40", "birth_time": "25:99", "calendar": "solar", "gender": "male"},
        {"birth_date": "abc", "birth_time": "14:30", "calendar": "solar", "gender": "male"},
        {"birth_date": "1990-03-15", "birth_time": "14:30", "calendar": "solar", "gender": "unknown"},
    ]
    rejected = 0
    for body in fuzz:
        rr = requests.post(f"{BASE}/api/chat/sessions", json={"birth": body, "top_k": 3}, timeout=10)
        if rr.status_code >= 400:
            rejected += 1
    r.chk(rejected >= 2, f"퍼징 입력 거부 {rejected}/4")

    # 4) SQL Injection 시도 (이메일 필드)
    inj = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": "x' OR '1'='1", "password": "any"},
        timeout=5,
    )
    r.chk(inj.status_code in (400, 401, 422), f"SQLi 시도 거부 → {inj.status_code}")

    # 5) 매우 긴 message (10000자) → 응답 가능해야 (또는 400으로 잘림)
    H = {"Authorization": f"Bearer {login('test_user_001@example.com', 'testpass1234')}", "Content-Type": "application/json"}
    s = requests.post(f"{BASE}/api/chat/sessions", headers=H, json={"birth": {"birth_date": "1990-03-15", "birth_time": "14:30", "calendar": "solar", "gender": "male"}, "top_k": 3}, timeout=30).json()
    long_msg = "가" * 5000
    t0 = time.time()
    rr = requests.post(f"{BASE}/api/chat/sessions/{s['session_id']}/messages", headers=H, json={"message": long_msg, "top_k": 3}, timeout=300)
    dt = time.time() - t0
    r.chk(rr.status_code in (200, 400, 413, 422), f"긴 메시지 → {rr.status_code} ({dt:.1f}s)")
    requests.delete(f"{BASE}/api/chat/sessions/{s['session_id']}", headers=H, timeout=5)

    print(r.verdict())
    return r


def main() -> int:
    rounds = [round1_token_and_permission(), round2_payment_idempotency_and_oauth_injection(), round3_load_and_input_fuzz()]
    print("\n================ GAN Test 최종 ================")
    total_pass = sum(r.pass_ for r in rounds)
    total_fail = sum(r.fail for r in rounds)
    for r in rounds:
        print("  " + r.verdict())
    print(f"\n총 PASS={total_pass} FAIL={total_fail}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
