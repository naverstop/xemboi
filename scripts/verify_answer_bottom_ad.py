"""사용자 질문 → 답변 → answer_bottom 배너 노출 가능 여부를 한 흐름으로 확인."""
from __future__ import annotations

import requests

BASE = "http://127.0.0.1:8000"


def main() -> None:
    # 비로그인 사용자도 채팅 가능 + 광고 노출됨
    s = requests.post(
        f"{BASE}/api/chat/sessions",
        json={
            "birth": {"birth_date": "1990-03-15", "birth_time": "14:30", "calendar": "solar", "gender": "male"},
            "top_k": 3,
        },
        timeout=30,
    ).json()
    sid = s["session_id"]
    print(f"[1] 세션 생성 OK sid={sid[:12]}…")

    m = requests.post(
        f"{BASE}/api/chat/sessions/{sid}/messages",
        json={"message": "올해 운세 봐줘", "top_k": 3},
        timeout=300,
    ).json()
    ans_len = len(m.get("answer", ""))
    print(f"[2] 답변 수신 OK answer={ans_len}자, is_preview={m.get('is_preview')}, billing={m.get('billing_mode')}")

    # answer_bottom 슬롯 fetch (프론트가 답변 직후 호출하는 것과 동일)
    b = requests.get(f"{BASE}/api/banners?slot=answer_bottom&pick_one=true", timeout=5).json()
    items = b.get("items", [])
    print(f"[3] answer_bottom 배너 {len(items)}건")
    for x in items:
        print(f"    - id={x['id']} slot={x['slot']} weight={x['weight']}")
        print(f"      image={x['image_url']}")
        print(f"      link={x.get('link_url')}")

    # 모든 슬롯 일괄
    print("\n[4] 모든 슬롯 현황")
    for slot in ("top", "chat_top_1", "chat_top_2", "side_1", "side_2", "answer_bottom"):
        r = requests.get(f"{BASE}/api/banners?slot={slot}", timeout=5).json()
        print(f"    {slot:14s} → {len(r.get('items', []))}건")

    # 비로그인은 ads_hidden 없음 → 노출, 결제 사용자는 숨김 (정책 확인)
    print("\n[5] 결제 사용자(ads_hidden=true)는 BannerSlot 컴포넌트가 null 반환 → API 호출조차 안 함")


if __name__ == "__main__":
    main()
