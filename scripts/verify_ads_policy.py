"""광고 정책 검증.
- 비로그인: 노출
- 잔액>0: hidden
- 잔액0: 노출
- 잔액0 + admin 강제 hidden=true: hidden
- 강제 hidden=false 후 잔액0: 노출
- 잔액 충전 → hidden 자동
"""
from __future__ import annotations
import random
import requests

BASE = "http://127.0.0.1:8000"


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

    # 1) 비로그인 → 401
    r = requests.get(f"{BASE}/api/auth/me")
    chk(r.status_code == 401, "비로그인 me=401")

    # 2) 신규 가입 (signup_bonus 1000)
    email = f"adstest_{random.randint(1, 10**8)}@ex.com"
    reg = requests.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": "testpass1234"},
    ).json()
    H = {"Authorization": f"Bearer {reg['access_token']}"}
    me1 = requests.get(f"{BASE}/api/auth/me", headers=H).json()
    chk(me1["balance"] >= 1000 and me1["ads_hidden"] is True, f"신규(잔액{me1['balance']}) → hidden=True")

    # 3) 관리자 로그인 → 차감으로 잔액 0
    adm = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": "orion0321@gmail.com", "password": "!thdwlstn00"},
    ).json()
    HA = {"Authorization": f"Bearer {adm['access_token']}"}

    requests.post(
        f"{BASE}/api/admin/users/{me1['id']}/grant",
        headers=HA,
        json={"delta": -me1["balance"], "reason": "admin_grant"},
    )
    me2 = requests.get(f"{BASE}/api/auth/me", headers=H).json()
    chk(me2["balance"] == 0 and me2["ads_hidden"] is False, f"잔액 0 → hidden=False (실제 {me2['ads_hidden']})")

    # 4) 관리자가 강제 hidden=true
    r = requests.patch(
        f"{BASE}/api/admin/users/{me1['id']}/ads",
        headers=HA,
        json={"ads_hidden": True},
    ).json()
    chk(r["ads_hidden"] is True, "admin PATCH ads=true 반환")
    me3 = requests.get(f"{BASE}/api/auth/me", headers=H).json()
    chk(me3["balance"] == 0 and me3["ads_hidden"] is True, f"잔액0 + 강제 hidden → True (실제 {me3['ads_hidden']})")

    # 5) admin이 다시 hidden=false → 잔액0이므로 노출
    requests.patch(
        f"{BASE}/api/admin/users/{me1['id']}/ads",
        headers=HA,
        json={"ads_hidden": False},
    )
    me4 = requests.get(f"{BASE}/api/auth/me", headers=H).json()
    chk(me4["ads_hidden"] is False, f"강제 해제 → False (실제 {me4['ads_hidden']})")

    # 6) 잔액 5000 충전 → 자동 hidden
    requests.post(
        f"{BASE}/api/admin/users/{me1['id']}/grant",
        headers=HA,
        json={"delta": 5000, "reason": "admin_grant"},
    )
    me5 = requests.get(f"{BASE}/api/auth/me", headers=H).json()
    chk(me5["balance"] == 5000 and me5["ads_hidden"] is True, f"잔액 5000 → 자동 hidden=True (실제 {me5['ads_hidden']})")

    # 7) AdminUser 목록에 ads_hidden 필드 포함
    ul = requests.get(f"{BASE}/api/admin/users?q={email}", headers=HA).json()
    rowfor = next((u for u in ul["items"] if u["id"] == me1["id"]), None)
    chk(rowfor is not None and "ads_hidden" in rowfor, "AdminUser 응답에 ads_hidden 포함")

    print(f"\n총 PASS={pass_} FAIL={fail}")


if __name__ == "__main__":
    main()
