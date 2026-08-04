# -*- coding: utf-8 -*-
"""명리 도감 휠(MyeongriWheel) 노드 메달리온 베이크 — 오행 5색 양각 디스크 + 중앙 허브 (FLUX schnell).

운영자 요청: 휠이 밍밍함 → 양각·럭셔리. FLUX는 한자를 깨뜨리므로 **글자 없는 메달리온 베이스**만
굽고 甲乙丙…·子丑寅… 글자는 프론트 텍스트(웹폰트)로 얹는다(부적·명식패널과 동일 원칙).
중심부는 매끈하게 비워 글자 가독 확보. 스타일 앵커는 make_menu_icons.py(금·칠보 메달리온)와 통일.

주의: GPU0(쇼츠 자원) 유휴 시에만 — VRAM 게이트(8GB). GPU1은 LLM 서빙이라 사용 금지.
선별분은 frontend/public/wheel/el_{오행}.jpg + hub.jpg (220px q88).
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
OUT = r"D:\saju_agent\image\wheel_medallions"
os.makedirs(OUT, exist_ok=True)

# 양각(embossed relief) 메달리온 — 중앙은 텍스트용으로 매끈하게 비움. 글자 절대 금지.
BASE = ("luxurious circular medallion coin viewed straight from the front, perfectly centered, "
        "polished 3D embossed relief, ornate gold metal rim engraved with korean traditional "
        "cloud and wave motif, smooth plain glossy enamel center area completely empty, "
        "soft studio lighting with gentle specular glow, clean soft ivory white background, "
        "ultra detailed jewelry photography, high quality render, no text, no letters, no symbols")

THEMES = {
    "wood":  "deep emerald green jade enamel medallion",           # 목
    "fire":  "deep crimson red enamel medallion with warm glow",   # 화
    "earth": "rich amber ochre enamel medallion",                  # 토
    "metal": "bright platinum white silver enamel medallion",      # 금
    "water": "deep sapphire navy blue enamel medallion",           # 수
    "hub":   "grand ivory pearl enamel medallion with sapphire and gold double rim, slightly larger ornate border",  # 중앙 허브
}

pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)

for key, theme in THEMES.items():
    for seed in (7, 42):
        out = os.path.join(OUT, f"{key}_seed{seed}.png")
        if os.path.exists(out):
            continue
        t = time.time()
        img = pipe(prompt=f"{theme}, {BASE}", width=768, height=768, num_inference_steps=4,
                   guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"{key} seed{seed} ({time.time()-t:.0f}s)", flush=True)
print("done", flush=True)
