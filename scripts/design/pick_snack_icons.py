# -*- coding: utf-8 -*-
"""무료 테스트 아이콘 채택 — 검토로 고른 후보를 512px webp 로 배포.

사용: C:/shorts/.venv/Scripts/python.exe scripts/design/pick_snack_icons.py
  (Pillow 만 있으면 되므로 프로젝트 .venv 로도 동작)

입력 : D:\\saju_agent\\image\\snack_icons\\<원본파일명>.png
출력 : D:\\saju_agent\\frontend\\public\\snack\\{key}.webp
        · 결과 배지: {test_id}_{result_key}.webp  (snack_service.run_test 의 icon 경로)
        · 허브 카드: hub_{test_id}.webp           (api/snack.list_tests 의 icon 경로)

512px 인 이유: 프론트 배지 168px·허브 84px, 공유카드 500px 로 그려 둘 다 선명하면서 가볍다.

채택 근거(1차 22장 + 재생성 검토):
  · siksang  : 1차 seed7 은 중앙에 정체불명 한자 글리프(CLIP 77토큰 초과로 'no text' 잘림) → fix23
  · bigyeop  : seed7 은 손가락이 뭉개져 '협업' 전달 실패 → seed42(맞잡은 두 손)
  · inseong  : '펼친 책'이 가로 장면+가짜 글자로 반복 실패 → 소재를 인장/모래시계로 교체
"""
import os, sys
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"D:\saju_agent\image\snack_icons"
DST = r"D:\saju_agent\frontend\public\snack"
SIZE = 512

# 배포 key -> 채택 원본 파일명(확장자 제외)
CHOSEN = {
    # ── 재물(財) 6유형 ──
    "wealth_pyeonjae":  "wealth_pyeonjae_seed7",    # 구르는 홍금 주사위
    "wealth_jeongjae":  "wealth_jeongjae_seed7",    # 비취 금전수 + 금화
    "wealth_siksang":   "wealth_siksang_fix23",     # 교차한 금붓 + 청색 물감
    "wealth_bigyeop":   "wealth_bigyeop_seed42",    # 맞잡은 두 손 + 보라 오브
    "wealth_inseong":   "wealth_inseong_hour42",    # 금 모래시계 + 금박 메달리온(느긋한 시간)
    "wealth_gwanseong": "wealth_gwanseong_seed7",   # 금기둥 + 저울(네이비)
    # ── 도화(桃花) 5등급 ──
    "dohwa_classic":    "dohwa_classic_seed7",      # 달빛 구름 속 백학
    "dohwa_cozy":       "dohwa_cozy_seed7",         # 김 오르는 금테 찻잔
    "dohwa_spark":      "dohwa_spark_seed7",        # 연분홍 복사꽃
    "dohwa_magnetic":   "dohwa_magnetic_seed7",     # 만개한 진홍 장미
    "dohwa_star":       "dohwa_star_seed7",         # 왕관 두른 금빛 별
    # ── 허브(테스트 목록) ──
    "hub_wealth":       "hub_wealth_seed7",         # 금화 가득한 홍금 보물함
    "hub_dohwa":        "hub_dohwa_seed7",          # 복사꽃 가지
}

os.makedirs(DST, exist_ok=True)
ok = miss = 0
for key, src_name in CHOSEN.items():
    src = os.path.join(SRC, f"{src_name}.png")
    if not os.path.exists(src):
        print(f"  MISS {src_name}.png  (key={key})", flush=True); miss += 1; continue
    im = Image.open(src).convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)
    out = os.path.join(DST, f"{key}.webp")
    im.save(out, "WEBP", quality=88, method=6)
    print(f"  {key}.webp  ({os.path.getsize(out)//1024}KB  <- {src_name})", flush=True)
    ok += 1

print(f"done: {ok} written, {miss} missing -> {DST}", flush=True)
