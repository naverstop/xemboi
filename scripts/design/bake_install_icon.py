# -*- coding: utf-8 -*-
"""사이드바 '앱 설치' 메뉴 아이콘 베이크 (FLUX schnell, 1회성) — make_menu_icons.py와 동일 스타일.
후보: image/menu_icons/install/seed{7,42}.png → 선별본은 place 규격(중앙 크롭→96px webp)으로
frontend/public/icons/menu/install.webp 배치.
주의: GPU0 유휴 시에만(VRAM 게이트 8GB). GPU1은 LLM 서빙 — 사용 금지.
"""
import os, subprocess, sys, time

sys.stdout.reconfigure(encoding="utf-8")

GATE_MB = 8000
free = int(subprocess.check_output(
    ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "--id=0"]
).decode().strip())
if free < GATE_MB:
    print(f"abort: GPU0 free {free}MB < {GATE_MB}MB", flush=True)
    sys.exit(1)
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from diffusers import FluxPipeline

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT = r"D:\saju_agent\image\menu_icons\install"
os.makedirs(OUT, exist_ok=True)

# make_menu_icons.py BASE 동일(스타일 통일)
BASE = ("luxurious app icon, single circular medallion emblem perfectly centered, "
        "polished 3D gold metal with deep sapphire blue enamel inlay, glossy jewel accents, "
        "ornate elegant korean traditional motif border, clean soft ivory white background, "
        "soft studio lighting with gentle glow, ultra detailed, high quality render, no text")
THEME = "elegant smartphone with a radiant golden download arrow descending onto its screen"

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
for seed in (7, 42):
    out = os.path.join(OUT, f"seed{seed}.png")
    if os.path.exists(out):
        continue
    img = pipe(prompt=f"{THEME}, {BASE}", width=768, height=768, num_inference_steps=4,
               guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    img.save(out)
    print(f"seed{seed} ({time.time()-t0:.0f}s)", flush=True)
print("done", flush=True)
