"""SSE 진짜 토큰 스트리밍 검증.

회원 시드 → 관리자 로그인(admin_full 모드) → 세션 생성 → /messages/stream 호출
→ event 라인 파싱 → chunk 이벤트가 다회 들어오는지(=진짜 토큰 스트리밍) 확인.
"""
from __future__ import annotations

import json
import sys
import time

import httpx


BASE = "http://127.0.0.1:8000"


def sse_iter(r: httpx.Response):
    event = "message"
    data_lines: list[str] = []
    for raw in r.iter_lines():
        line = raw  # already str in httpx
        if line == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event = "message"
            data_lines = []
            continue
        if line.startswith("event: "):
            event = line[7:].strip()
        elif line.startswith("data: "):
            data_lines.append(line[6:])


def main() -> int:
    timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
    with httpx.Client(base_url=BASE, timeout=timeout) as c:
        # admin 로그인 (시드된 계정)
        r = c.post("/api/auth/login", json={
            "email": "orion0321@gmail.com",
            "password": "!thdwlstn00",
        })
        if r.status_code != 200:
            print(f"[FAIL] admin login: {r.status_code} {r.text}")
            return 1
        token = r.json()["access_token"]
        H = {"Authorization": f"Bearer {token}"}

        # 세션 생성
        r = c.post("/api/chat/sessions", headers=H, json={
            "birth": {"birth_date": "1990-03-15", "birth_time": "14:30",
                      "calendar": "solar", "is_leap_month": False,
                      "gender": "male", "apply_true_solar_time": False},
        })
        if r.status_code != 201:
            print(f"[FAIL] create session: {r.status_code} {r.text}")
            return 1
        sid = r.json()["session_id"]
        print(f"session_id = {sid}")

        # 스트림 요청
        t0 = time.perf_counter()
        first_chunk_at: float | None = None
        chunk_count = 0
        total_chars = 0
        meta = None
        done = None
        with c.stream(
            "POST",
            f"/api/chat/sessions/{sid}/messages/stream",
            headers=H,
            json={"message": "내 사주에서 가장 강한 오행이 뭔가요? 짧게 답해주세요."},
        ) as r:
            if r.status_code != 200:
                print(f"[FAIL] stream HTTP {r.status_code}: {r.read().decode()}")
                return 1
            print(f"  Content-Type: {r.headers.get('content-type')}")
            for ev, data in sse_iter(r):
                if ev == "meta":
                    meta = json.loads(data)
                    print(f"  [meta] billing_mode={meta['billing_mode']} preview={meta['is_preview']} sources={len(meta['sources'])}")
                elif ev == "chunk":
                    if first_chunk_at is None:
                        first_chunk_at = time.perf_counter() - t0
                    chunk_count += 1
                    obj = json.loads(data)
                    total_chars += len(obj.get("text", ""))
                elif ev == "done":
                    done = json.loads(data)
                elif ev == "error":
                    print(f"  [error] {data}")
                    return 1
        elapsed = time.perf_counter() - t0
        print(f"  first chunk at  : {first_chunk_at*1000:.0f} ms" if first_chunk_at else "  no chunks")
        print(f"  total elapsed   : {elapsed*1000:.0f} ms")
        print(f"  chunk count     : {chunk_count}")
        print(f"  total chars     : {total_chars}")
        if done:
            print(f"  [done] full_len={done['full_length']} preview_len={done['preview_length']} "
                  f"credits={done['credits_charged']} bal={done['balance_after']}")

    if meta is None or done is None:
        print("[FAIL] meta/done 누락")
        return 1
    if meta["billing_mode"] != "admin_full":
        print(f"[WARN] expected admin_full, got {meta['billing_mode']}")
    # admin_full → 진짜 토큰 스트리밍: chunk_count > 5 기대 (1글자/조각 단위)
    if not meta["is_preview"] and chunk_count < 5:
        print(f"[FAIL] full 모드인데 chunk_count={chunk_count} (스트리밍이 안 됨)")
        return 1
    print("\n✅ SSE 진짜 토큰 스트리밍 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
