# -*- coding: utf-8 -*-
"""사주 '이 명식으로 1:1 상담' CTA용 럭셔리 엠블럼 베이크 (FLUX schnell, 1회성 오프라인).
의미 전달: 사주 명식(음양·오행) + 대화(말풍선) — "이 명식으로 상담사와 대화" 모티프.
따뜻한 아이보리+인디고+금박(밝은 브랜드 카드 위에 얹히는 CTA라 타로의 심야톤과 달리 밝게).
글자 금지(텍스트는 CSS 합성). GPU0(쇼츠) 유휴 시에만: VRAM 게이트로 자동 중단. GPU1=LLM은 미사용.
후보: D:\\saju_agent\\image\\saju_consult_badge\\seed{n}.png
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
OUT = r"D:\saju_agent\image\saju_consult_badge"
os.makedirs(OUT, exist_ok=True)

# '명식으로 나누는 대화' — 금박 말풍선 안의 음양(태극)+오행 우주, 해와 달. 밝은 아이보리+인디고+금.
PROMPT = ("luxurious circular medallion emblem, perfectly centered, "
          "an elegant golden speech bubble frame containing a traditional East Asian yin-yang taegeuk symbol, "
          "surrounded by a ring of five-element cosmology symbols, small radiant sun and crescent moon, "
          "polished 3D gold metal filigree with deep indigo blue and jade enamel inlay, art deco sunburst rays, "
          "glossy jewel accents, ornate elegant border, soft warm golden glow, "
          "warm ivory and soft indigo background, ultra detailed, premium render, no text, no letters")
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
