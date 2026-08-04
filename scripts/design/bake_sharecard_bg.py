# -*- coding: utf-8 -*-
"""B-6 오늘의운세 공유카드 배경 문양 베이크 (FLUX schnell, 1회성 오프라인).

목적: 기존 '밋밋한 아이보리 그라데이션' 배경을 프리미엄 그리팅카드 감성으로 교체(운영자 지시).
날짜·타이틀·12띠 아바타·일진·십성·행운색칩·브랜드·QR 은 전부 PIL이 그 위에 결정적으로 합성하므로,
배경은 '가운데가 밝고 비어 있는' 세로 스토리(9:16) 장식 프레임이어야 한다(글자 가독 보존).

컨셉 2종 × 시드 2 = 4장 → 후보 image/sharecard_bg/{concept}_seed{n}.png
선별본을 backend/app/services/assets/sharecard_bg.jpg 로 배치(서비스가 1080x1920 리사이즈).

주의: GPU0(쇼츠 자원) 유휴 시에만 — VRAM 게이트(8GB)로 자동 중단. GPU1은 LLM 서빙이라 사용 금지.
실행: C:\\shorts\\.venv\\Scripts\\python.exe scripts/design/bake_sharecard_bg.py
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
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from diffusers import FluxPipeline

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT = r"D:\saju_agent\image\sharecard_bg"
os.makedirs(OUT, exist_ok=True)

# 반드시 '밝은' 톤(합성 글자=진갈색/브랜드 블루라 어두운 배경이면 안 읽힘) + 중앙 비움.
BASE = ("elegant luxury greeting card background, bright warm ivory cream and soft champagne gold "
        "color palette, airy and luminous, {motif}, delicate gold filigree ornament framing only along "
        "the top and bottom edges and corners, large calm empty bright center space reserved for a "
        "portrait, soft radiant glow in the middle, premium wedding invitation aesthetic, subtle "
        "shimmering gold bokeh particles, tall vertical 9:16 composition, flat clean high quality, "
        "no text, no letters, no characters, no writing, no watermark, no frame in the center")

CONCEPTS = {
    # 전통 길상 — 은은한 구름·매화가 상하 테두리에만, 가운데는 환하게
    "ornate": "ornate art nouveau golden flourishes with subtle swirling auspicious korean clouds "
              "and faint plum blossom branches woven into the top and bottom borders",
    # 미니멀 럭셔리 — 얇은 금선 코너 + 보케만, 더 담백
    "softlux": "minimal refined thin gold line art corner ornaments and a faint concentric halo, "
               "very soft and understated, mostly clean empty cream space",
}
SEEDS = [7, 42]
W_, H_ = 1088, 1920   # 스토리 9:16(1080폭은 16배수 아님 → 1088로 굽고 서비스가 1080으로 리사이즈)

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"load {time.time()-t0:.0f}s", flush=True)

for key, motif in CONCEPTS.items():
    for seed in SEEDS:
        out = os.path.join(OUT, f"{key}_seed{seed}.png")
        if os.path.exists(out):
            print(f"  skip {key}_seed{seed}", flush=True)
            continue
        ts = time.time()
        img = pipe(prompt=BASE.format(motif=motif), width=W_, height=H_, num_inference_steps=4,
                   guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  {key}_seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s -> {OUT}", flush=True)
