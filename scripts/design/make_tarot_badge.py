# -*- coding: utf-8 -*-
"""타로 바로가기 배지용 럭셔리 엠블럼 베이크 (FLUX schnell, 1회성 오프라인).
미드나잇 골드 아틀리에(타로 페이지) 톤에 맞춤 — 심야 네이비 + 금박. 글자 없음(CSS로 TAROT 합성).
GPU0(쇼츠) 유휴 시에만: VRAM 게이트로 자동 중단. GPU1=LLM 서빙은 건드리지 않음.
후보: D:\\saju_agent\\image\\tarot_badge\\seed{n}.png
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
OUT = r"D:\saju_agent\image\tarot_badge"
os.makedirs(OUT, exist_ok=True)

# 타로 페이지 팔레트(심야 네이비 #0A0E24 + 금박 #C9A455)와 아르데코 카드백 결에 맞춘 원형 메달리온.
# 글자 금지(FLUX 텍스트 불안정) — 순수 엠블럼. 배경은 투명 크롭 쉽게 어두운 원형.
PROMPT = ("luxurious circular tarot medallion emblem, perfectly centered, "
          "an upright mystical tarot card with a radiant golden sun face, crescent moon and shining stars, "
          "polished 3D gold metal filigree with deep midnight navy blue enamel inlay, art deco sunburst rays, "
          "glossy jewel accents, ornate elegant border, soft golden glow, dark navy background, "
          "ultra detailed, premium render, no text, no letters")
SEEDS = [7, 21, 42, 99]
W = H = 1024

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"load {time.time()-t0:.0f}s", flush=True)

for seed in SEEDS:
    out = os.path.join(OUT, f"seed{seed}.png")
    if os.path.exists(out):
        print(f"  skip seed{seed}", flush=True); continue
    ts = time.time()
    img = pipe(prompt=PROMPT, width=W, height=H, num_inference_steps=4, guidance_scale=0.0,
               generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    img.save(out)
    print(f"  seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s -> {OUT}", flush=True)
