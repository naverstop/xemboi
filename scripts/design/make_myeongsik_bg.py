# -*- coding: utf-8 -*-
"""상담서 PDF 명식 패널 배경 베이크 (FLUX schnell, 1회성 오프라인).
따뜻한 원목 테두리 + 한지 질감의 '빈' 가로 패널 — 글자·격자는 PDF에서 결정적으로 그린다.
후보: image/myeongsik_bg/seed{n}.png → 선별본을 backend/app/services/assets/myeongsik_bg.jpg 로.

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
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from diffusers import FluxPipeline

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT = r"D:\saju_agent\image\myeongsik_bg"
os.makedirs(OUT, exist_ok=True)

PROMPT = ("empty traditional korean hanji paper panel framed by a warm polished dark wood border, "
          "aged ivory mulberry paper texture with subtle fibers, corners decorated with small elegant "
          "gold metal fittings, soft warm candlelight glow, gentle vignette, completely empty clean "
          "center area, luxurious antique calligraphy stationery feel, top-down flat view, "
          "no text, no letters, no writing, no objects")
SEEDS = [7, 21, 42, 77]
W_, H_ = 1152, 480  # PDF 패널 비율(~2.4:1), 16의 배수

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
        print(f"  skip seed{seed}", flush=True)
        continue
    ts = time.time()
    img = pipe(prompt=PROMPT, width=W_, height=H_, num_inference_steps=4, guidance_scale=0.0,
               generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    img.save(out)
    print(f"  seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s -> {OUT}", flush=True)
