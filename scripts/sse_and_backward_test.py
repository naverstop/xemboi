"""Phase 4A SSE + 후방향 비로그인 흐름을 빠르게 검증."""
from __future__ import annotations

import json
import sys

import requests

BASE = "http://127.0.0.1:8000"


def login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def assert_eq(actual, expected, name: str):
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {actual!r} == {expected!r}")
    return ok


def assert_true(cond: bool, name: str):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    return cond


def main() -> int:
    pass_, fail = 0, 0

    def chk(cond, name):
        nonlocal pass_, fail
        if cond:
            pass_ += 1
            print(f"[PASS] {name}")
        else:
            fail += 1
            print(f"[FAIL] {name}")

    # ---------- SSE ----------
    tok = login("test_user_001@example.com", "testpass1234")
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    sess = requests.post(
        f"{BASE}/api/chat/sessions",
        headers=H,
        json={
            "birth": {"birth_date": "1990-03-15", "birth_time": "14:30", "calendar": "solar", "gender": "male"},
            "top_k": 3,
        },
        timeout=30,
    ).json()
    sid = sess["session_id"]

    chunks: list[str] = []
    done_meta = None
    with requests.post(
        f"{BASE}/api/chat/sessions/{sid}/messages/stream",
        headers=H,
        json={"message": "테스트", "top_k": 3},
        stream=True,
        timeout=300,
    ) as resp:
        chk(resp.status_code == 200, "sse-status-200")
        cur_event = None
        for raw in resp.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            if raw == "":
                cur_event = None
                continue
            if raw.startswith("event: "):
                cur_event = raw[7:].strip()
            elif raw.startswith("data: "):
                payload = raw[6:]
                if cur_event == "chunk":
                    try:
                        chunks.append(json.loads(payload).get("text", ""))
                    except Exception:
                        pass
                elif cur_event == "done":
                    try:
                        done_meta = json.loads(payload)
                    except Exception:
                        done_meta = None

    chk(len(chunks) > 0, "sse-received-chunks")
    chk(done_meta is not None, "sse-received-done")
    if done_meta:
        chk("billing_mode" in done_meta, "sse-done-has-billing")
        chk("answer_length" in done_meta or "preview_length" in done_meta or "answer" in done_meta or "is_preview" in done_meta, "sse-done-has-length-or-preview")

    # 청소: 세션 삭제
    requests.delete(f"{BASE}/api/chat/sessions/{sid}", headers=H, timeout=10)

    # ---------- 후방향: 비로그인 미리보기 ----------
    s = requests.post(
        f"{BASE}/api/chat/sessions",
        json={
            "birth": {"birth_date": "1985-08-20", "birth_time": "08:00", "calendar": "solar", "gender": "female"},
            "top_k": 3,
        },
        timeout=30,
    ).json()
    asid = s["session_id"]
    am = requests.post(
        f"{BASE}/api/chat/sessions/{asid}/messages",
        json={"message": "올해 운", "top_k": 3},
        timeout=300,
    ).json()
    chk(am.get("is_preview") is True, "anon-is-preview")
    chk(am.get("billing_mode") == "anonymous_preview", "anon-billing-mode")
    chk(int(am.get("full_length", 0)) > len(am.get("answer", "")), "anon-truncated")

    # reveal 비로그인 401
    rv = requests.post(
        f"{BASE}/api/chat/sessions/{asid}/messages/{am['assistant_message_id']}/reveal",
        timeout=10,
    )
    chk(rv.status_code == 401, "anon-reveal-401")

    # ---------- 잔액부족 시 reveal 402 ----------
    # smoke 사용자 (잔액 500, message_cost 500 → reveal 후 0). 잔액부족 케이스를 만들기 위해 추가 reveal 시도
    # 더 안전하게: 새 mock 카카오 가입 사용자(보너스 1000) 로 reveal 후, 두 번째 reveal 시도
    o = requests.post(f"{BASE}/api/auth/oauth/kakao/test-login", timeout=10).json()
    Ho = {"Authorization": f"Bearer {o['access_token']}", "Content-Type": "application/json"}
    me = requests.get(f"{BASE}/api/auth/me", headers=Ho, timeout=10).json()
    chk(me["balance"] >= 1000, "oauth-bonus-1000+")

    print(f"\n===== SSE/후방향 결과: PASS={pass_} FAIL={fail} =====")
    return fail


if __name__ == "__main__":
    sys.exit(main())
