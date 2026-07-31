"""End-to-end smoke test: 인증 + 빌링 (anonymous/daily_free/paid/admin)."""
from __future__ import annotations

import json
import time

import httpx

BASE = "http://127.0.0.1:8000"

BIRTH = {
    "birth": {
        "birth_date": "1990-03-15",
        "birth_time": "14:30:00",
        "calendar": "solar",
        "gender": "male",
    },
    "top_k": 4,
}
Q = "내 사주에서 일간의 강약과 용신을 간단히 알려줘."


def hr(t: str) -> None:
    print(f"\n=== {t} ===")


def call(method: str, path: str, *, token: str | None = None, json_body=None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.request(method, BASE + path, headers=headers, json=json_body, timeout=300.0)
    try:
        body = r.json()
    except Exception:
        body = {"_raw": r.text[:300]}
    return {"status": r.status_code, "body": body}


def main() -> None:
    ts = int(time.time())
    user_email = f"smoke_{ts}@ex.com"
    user_pw = "smokepass1234"

    # ---- 1) 익명 세션 ----
    hr("1. anonymous create session")
    r = call("POST", "/api/chat/sessions", json_body=BIRTH)
    print(r["status"])
    sid_anon = r["body"]["session_id"]
    print("sid=", sid_anon)

    hr("2. anonymous post message (preview 기대)")
    r = call("POST", f"/api/chat/sessions/{sid_anon}/messages", json_body={"message": Q})
    b = r["body"]
    print("status=", r["status"], "billing=", b.get("billing_mode"),
          "is_preview=", b.get("is_preview"),
          "full_len=", b.get("full_length"), "preview_len=", b.get("preview_length"),
          "charged=", b.get("credits_charged"))
    print("answer head:", b.get("answer", "")[:80])
    mid_anon = b.get("assistant_message_id")

    hr("3. anonymous reveal (401 기대)")
    r = call("POST", f"/api/chat/sessions/{sid_anon}/messages/{mid_anon}/reveal")
    print("status=", r["status"], r["body"])

    # ---- 4) 회원 가입 ----
    hr("4. register user")
    r = call("POST", "/api/auth/register", json_body={"email": user_email, "password": user_pw})
    print(r["status"], r["body"].get("role"))
    tok = r["body"]["access_token"]
    me = call("GET", "/api/auth/me", token=tok)["body"]
    print("me balance=", me["balance"], "daily_free=", me["daily_free_available"])

    # ---- 5) 회원 세션 + 1일 무료 질문 (preview 기대) ----
    hr("5. user create session + daily_free message")
    sid = call("POST", "/api/chat/sessions", token=tok, json_body=BIRTH)["body"]["session_id"]
    r = call("POST", f"/api/chat/sessions/{sid}/messages", token=tok, json_body={"message": Q})
    b = r["body"]
    print("status=", r["status"], "billing=", b.get("billing_mode"),
          "is_preview=", b.get("is_preview"),
          "full=", b.get("full_length"), "preview=", b.get("preview_length"),
          "charged=", b.get("credits_charged"), "balance=", b.get("balance_after"))
    mid = b["assistant_message_id"]

    hr("6. user reveal preview (500P 차감 기대)")
    r = call("POST", f"/api/chat/sessions/{sid}/messages/{mid}/reveal", token=tok)
    print("status=", r["status"], "charged=", r["body"].get("credits_charged"),
          "balance=", r["body"].get("balance_after"),
          "content_len=", len(r["body"].get("content", "")))

    # ---- 7) 두 번째 질문 → daily_free 소진 → paid 1000P 차감 기대 ----
    hr("7. user 2nd message (paid_full 기대)")
    r = call("POST", f"/api/chat/sessions/{sid}/messages", token=tok,
             json_body={"message": "내 대운 흐름을 짧게 설명해줘."})
    b = r["body"]
    print("status=", r["status"], "billing=", b.get("billing_mode"),
          "is_preview=", b.get("is_preview"),
          "charged=", b.get("credits_charged"), "balance=", b.get("balance_after"))

    # ---- 8) 잔액 소진 후 402 기대 (잔액이 1000 이상이면 차감 반복) ----
    hr("8. drain balance until 402")
    for i in range(6):
        r = call("POST", f"/api/chat/sessions/{sid}/messages", token=tok,
                 json_body={"message": f"질문{i}: 한 줄로 답해줘."})
        b = r["body"]
        print(f"  try{i}: status={r['status']} billing={b.get('billing_mode')} balance={b.get('balance_after')} detail={b.get('detail')}")
        if r["status"] == 402:
            break

    # ---- 9) 관리자 admin_full 기대 ----
    hr("9. admin login + post message (admin_full 기대)")
    adm = call("POST", "/api/auth/login",
               json_body={"email": "orion0321@gmail.com", "password": "!thdwlstn00"})["body"]
    atok = adm["access_token"]
    sid_a = call("POST", "/api/chat/sessions", token=atok, json_body=BIRTH)["body"]["session_id"]
    r = call("POST", f"/api/chat/sessions/{sid_a}/messages", token=atok,
             json_body={"message": "한 줄 요약 부탁."})
    b = r["body"]
    print("status=", r["status"], "billing=", b.get("billing_mode"),
          "is_preview=", b.get("is_preview"),
          "charged=", b.get("credits_charged"), "balance=", b.get("balance_after"))


if __name__ == "__main__":
    main()
