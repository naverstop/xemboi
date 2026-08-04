# -*- coding: utf-8 -*-
"""사이드바 메뉴 13종 럭셔리 아이콘 베이크 (FLUX schnell, 1회성 오프라인).
scripts/design/bake_web_illust.py 와 동일 파이프라인/게이트. 메뉴 특징을 금·칠보 메달리온 엠블럼으로.
후보를 D:\\saju_agent\\image\\menu_icons\\{key}\\seed{n}.png 로 저장, 선별분은 별도 후처리로
frontend/public/icons/menu/ 에 배치.

주의: GPU0(쇼츠 자원) 유휴 시에만 실행 — VRAM 게이트(8GB)로 자동 중단. GPU1은 LLM 서빙 중이라 사용 금지.
"""
import os, subprocess, sys, time

sys.stdout.reconfigure(encoding="utf-8")

GATE_MB = 8000
free = int(subprocess.check_output(
    ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "--id=0"]
).decode().strip())
if free < GATE_MB:
    print(f"abort: GPU0 free {free}MB < {GATE_MB}MB (쇼츠 작업 중일 수 있음)", flush=True)
    sys.exit(1)
os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # 1회성 베이크: 유휴 GPU0 사용(GPU1=LLM 서빙 회피)

import torch
from diffusers import FluxPipeline

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT_ROOT = r"D:\saju_agent\image\menu_icons"
os.makedirs(OUT_ROOT, exist_ok=True)

# 스타일 앵커 — 사이트 팔레트(하늘빛 브랜드+금 포인트)와 12띠/기능 일러스트의 고급 3D 렌더 결에 맞춤.
# 원형 메달리온으로 통일해 CSS 원형 크롭과 일치시킨다. 글자 금지(FLUX 한글 불가) — 순수 도형 엠블럼만.
BASE = ("luxurious app icon, single circular medallion emblem perfectly centered, "
        "polished 3D gold metal with deep sapphire blue enamel inlay, glossy jewel accents, "
        "ornate elegant korean traditional motif border, clean soft ivory white background, "
        "soft studio lighting with gentle glow, ultra detailed, high quality render, no text")

# 메뉴 13종 — 각 메뉴의 '특징'을 모티프로
THEMES = {
    "chat":     "golden speech bubble with a small radiant star inside",            # 상담
    "gunghap":  "two intertwined golden hearts with red thread of fate ribbon",     # 궁합
    "taekil":   "traditional lunar calendar page with crescent moon and sun",       # 택일
    "jakmyeong": "ink calligraphy brush crossing a glowing scroll",                 # 작명
    "gaemyeong": "phoenix rising in a circular renewal arrow",                      # 개명
    "aho":      "red square seal stamp with gold handle, ink paste box",            # 아호
    "tarot":    "mystical tarot card with radiant star and crescent moon",          # 타로
    "bolt":     "lightning bolt striking a stack of gold coins",                    # 충전
    "gear":     "ornate clockwork gear with jewel center",                          # 설정
    "folder":   "open scroll case with documents and upward golden arrow",          # 업로드
    "chart":    "rising line chart with golden arrow and sparkles",                 # 평가 추세
    "wrench":   "ornate golden master key with royal crown bow",                    # 관리자
    "mail":     "cream envelope sealed with red wax stamp",                         # 고객센터
    # ── 2026-07 로드맵 신규 메뉴 7종 (기존 키는 skip-if-exists 라 재베이크 안 됨) ──
    "today":    "radiant golden rising sun over an open daily calendar page",       # 오늘의 운세
    "fcalendar": "monthly grid calendar with tiny jewel date marks and golden star",  # 운세 캘린더
    "sinnyeon": "elegant red horse head medallion with golden new year sunrise",    # 신년운세(병오년)
    "amulet":   "vertical golden yellow talisman paper with red ornamental pattern",  # 부적
    "dream":    "crescent moon sleeping on soft clouds with sparkling stars",       # 꿈해몽
    "snack":    "playful golden star badge with confetti ribbons and tiny hearts",  # 무료 테스트
    "reviews":  "cream speech bubble with five small golden rating stars",          # 이용 후기
}
SEEDS = [7, 42]
W = H = 512  # 사이드바 26px 표시용 — 512 충분, 속도 우선

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"load {time.time()-t0:.0f}s", flush=True)

for key, theme in THEMES.items():
    kdir = os.path.join(OUT_ROOT, key)
    os.makedirs(kdir, exist_ok=True)
    for seed in SEEDS:
        out = os.path.join(kdir, f"seed{seed}.png")
        if os.path.exists(out):
            print(f"  skip {key}/seed{seed}", flush=True)
            continue
        ts = time.time()
        prompt = f"{theme}, {BASE}"
        img = pipe(prompt=prompt, width=W, height=H, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  {key}/seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s ({len(THEMES)*len(SEEDS)}장) -> {OUT_ROOT}", flush=True)
