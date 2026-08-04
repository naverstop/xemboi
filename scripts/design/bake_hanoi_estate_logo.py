# -*- coding: utf-8 -*-
"""[별건] 하노이 온라인 부동산 · Hanoi Estate 로고 베이크 (FLUX schnell, 1회성).

브랜드 브리프(Rev.2): 아이보리/크림 바탕 · 샴페인 브라스 헤어라인 · 타이포+여백 중심 · 조용한 럭셔리.
2D 2컨셉(모노그램 HE · 절제된 아치 엠블럼) + 3D 2컨셉, 시드 7/42 → 후보 8장.
출력: D:\\saju_agent\\image\\hanoi_estate\\{2d|3d}_{concept}_seed{n}.png
주의: GPU0 유휴 시에만(VRAM 8GB 게이트). GPU1은 LLM 서빙 — 사용 금지.
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
OUT = r"D:\saju_agent\image\hanoi_estate"
os.makedirs(OUT, exist_ok=True)

# 공통 아트디렉션 — 조용한 럭셔리지만 눈에 띄게(대비 있는 브라스, 선명한 형태)
BASE_2D = ("minimalist luxury logo, flat 2D vector emblem, clean warm ivory cream background, "
           "elegant champagne brass and deep charcoal, crisp refined lines, high-end real estate "
           "brand identity, quiet luxury, generous negative space, editorial, perfectly centered, "
           "sharp, professional, high quality")
BASE_3D = ("luxury 3D logo emblem, polished champagne brass metal with soft satin finish, "
           "embossed dimensional, gentle studio lighting and subtle reflections, clean warm ivory "
           "cream background, high-end real estate brand, premium product render, elegant, "
           "perfectly centered, ultra detailed, high quality")

CONCEPTS = {
    # (style, concept): theme prompt
    ("2d", "mono"): (
        "an elegant interlocking monogram of the capital letters H and E, refined thin serif "
        "letterforms in champagne brass with a single hairline underline, timeless real estate "
        "monogram, " + BASE_2D),
    ("2d", "arch"): (
        "a minimal abstract emblem of a stately building facade with a tall elegant arched doorway, "
        "drawn as a single continuous thin brass hairline, symmetrical, luxury real estate mark, "
        "no letters, no text, " + BASE_2D),
    ("3d", "mono"): (
        "a three dimensional interlocking monogram of the capital letters H and E, polished brass "
        "metal, embossed and beveled, sitting on an elegant thin brass baseline, luxury real estate "
        "emblem, " + BASE_3D),
    ("3d", "arch"): (
        "a three dimensional emblem of a stately building facade with a tall elegant archway, "
        "sculpted in brushed brass metal, embossed relief, symmetrical, luxury real estate mark, "
        "no letters, no text, " + BASE_3D),
}
SEEDS = (7, 42)

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)

for (style, concept), prompt in CONCEPTS.items():
    for seed in SEEDS:
        out = os.path.join(OUT, f"{style}_{concept}_seed{seed}.png")
        if os.path.exists(out):
            print(f"skip {os.path.basename(out)}", flush=True)
            continue
        img = pipe(prompt=prompt, width=1024, height=1024, num_inference_steps=4,
                   guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"{style}_{concept}_seed{seed} ({time.time()-t0:.0f}s)", flush=True)
print("done", flush=True)
