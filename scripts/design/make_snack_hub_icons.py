# -*- coding: utf-8 -*-
"""무료 테스트 '허브'(테스트 목록) 카드 아이콘 2종 베이크 (FLUX schnell, 1회성).

허브도 이모지(💰/🌸)라 결과 일러스트와 격이 안 맞아 함께 교체한다.
결과 아이콘(make_snack_icons.py)과 같은 스타일 문구를 공유해 한 세트로 보이게 한다.
결과가 '개별 성향'이라면 허브는 '테스트 주제' 대표 엠블럼.

출력: D:\\saju_agent\\image\\snack_icons\\hub_{test_id}_seed{n}.png
실행: C:/shorts/.venv/Scripts/python.exe scripts/design/make_snack_hub_icons.py
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
OUT = r"D:\saju_agent\image\snack_icons"
os.makedirs(OUT, exist_ok=True)

STYLE = ("luxurious circular medallion emblem, perfectly centered composition, "
         "polished 3D gold metal filigree linework, glossy jewel enamel inlay, "
         "ornate elegant ring border, soft radiant glow, warm ivory background, "
         "korean traditional-modern fusion, ultra detailed, premium render, "
         "no text, no letters, no words, no numbers")

SUBJECTS = [
    ("hub_wealth",      # 타고난 재물 기질 — 재물 주제 대표
     "an ornate golden treasure vessel overflowing with glowing coins and gemstones, "
     "radiant prosperity aura, deep crimson and rich gold, wealth fortune"),
    ("hub_dohwa",       # 내 도화 매력 등급 — 매력/도화 주제 대표
     "a blooming peach blossom branch with soft luminous petals drifting, "
     "delicate romantic aura, rose pink and gold, charm and attraction"),
]

SEEDS = [7, 42]
W = H = 1024

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"load {time.time()-t0:.0f}s", flush=True)

for key, subject in SUBJECTS:
    prompt = f"{subject}, {STYLE}"
    for seed in SEEDS:
        out = os.path.join(OUT, f"{key}_seed{seed}.png")
        if os.path.exists(out):
            print(f"  skip {key}_seed{seed}", flush=True); continue
        ts = time.time()
        img = pipe(prompt=prompt, width=W, height=H, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  {key}_seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s -> {OUT}", flush=True)
