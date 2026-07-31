"""로그아웃(클라 only, 데이터 유지) + 탈퇴(서버 완전 삭제) 검증."""
from __future__ import annotations
import random
import requests

BASE = "http://127.0.0.1:8000"

REG_DEFAULTS = {
    "birth_date": "1990-05-15",
    "agree_terms": True,
    "agree_privacy": True,
    "agree_refund": True,
}


def _reg(email: str, pw: str):
    body = {"email": email, "password": pw, **REG_DEFAULTS}
    return requests.post(f"{BASE}/api/auth/register", json=body)


def main() -> None:
    pass_, fail = 0, 0

    def chk(cond, label):
        nonlocal pass_, fail
        if cond:
            pass_ += 1
            print(f"[PASS] {label}")
        else:
            fail += 1
            print(f"[FAIL] {label}")

    # ---- 시나리오 1: 로그아웃 후 재로그인 → 채팅 세션 유지 ----
    email = f"logout_{random.randint(1, 10**8)}@ex.com"
    pw = "testpass1234"
    tok = _reg(email, pw).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    # 세션 + 메시지 생성
    s = requests.post(
        f"{BASE}/api/chat/sessions",
        headers=H,
        json={"birth": {"birth_date": "1990-03-15", "birth_time": "14:30", "calendar": "solar", "gender": "male"}, "top_k": 3},
    ).json()
    sid = s["session_id"]
    sess_before = requests.get(f"{BASE}/api/chat/sessions?limit=10", headers=H).json()
    chk(any(it["session_id"] == sid for it in sess_before["items"]), "로그인 상태 세션 노출")

    # 로그아웃 = 클라가 토큰만 버림 → 서버 상태 변화 없음. 재로그인.
    tok2 = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}).json()["access_token"]
    H2 = {"Authorization": f"Bearer {tok2}"}
    sess_after = requests.get(f"{BASE}/api/chat/sessions?limit=10", headers=H2).json()
    chk(any(it["session_id"] == sid for it in sess_after["items"]), "재로그인 후 세션 유지")

    # ---- 시나리오 2: 탈퇴 → 모든 데이터 삭제, 재로그인 불가 ----
    rdel = requests.delete(f"{BASE}/api/auth/me", headers=H2)
    chk(rdel.status_code == 204, f"DELETE /api/auth/me → 204 (실제 {rdel.status_code})")

    # 동일 토큰으로 me 조회 → 401
    me_after = requests.get(f"{BASE}/api/auth/me", headers=H2)
    chk(me_after.status_code == 401, f"탈퇴 후 토큰 무효 → 401 (실제 {me_after.status_code})")

    # 동일 email로 재로그인 → 401
    relogin = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    chk(relogin.status_code == 401, f"탈퇴 계정 재로그인 → 401 (실제 {relogin.status_code})")

    # 동일 email로 재가입 가능
    new_reg = _reg(email, pw)
    chk(new_reg.status_code == 200, f"동일 email 재가입 가능 → 200 (실제 {new_reg.status_code})")
    new_tok = new_reg.json()["access_token"]
    H3 = {"Authorization": f"Bearer {new_tok}"}
    # 신규 가입자라 채팅 세션 없음
    sess_new = requests.get(f"{BASE}/api/chat/sessions?limit=10", headers=H3).json()
    chk(len(sess_new["items"]) == 0, f"재가입 계정은 채팅 히스토리 없음 (실제 {len(sess_new['items'])}건)")

    print(f"\n총 PASS={pass_} FAIL={fail}")


if __name__ == "__main__":
    main()
