# -*- coding: utf-8 -*-
"""관리형(inseong) 아이콘 재시도 — 소재 교체.

'펼친 책'은 필연적으로 가로로 넓은 장면이 되어 원형 크롭에서 잘리고, 책장에 가짜 글자가
생기는 문제가 반복됐다(fix11/23/42 전부 탈락). 소재를 원형 친화적인 것으로 바꾼다:
  A) 금 인장(印) — 인성(印星)의 글자 뜻 그대로. 면은 문양으로(글자 금지).
  B) 금 모래시계 — '느긋한 관리형'의 여유·시간 상징. 세로형이라 원형에 잘 앉는다.

출력: D:\\saju_agent\\image\\snack_icons\\wealth_inseong_{variant}{seed}.png
실행: C:/shorts/.venv/Scripts/python.exe scripts/design/fix_snack_inseong.py
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

# 'no text' 를 맨 앞에 둬 CLIP 77토큰 잘림에도 살아남게 함
STYLE = "no text, circular gold medallion emblem, centered, gold filigree ring, ivory background, premium 3d render"

SUBJECTS = [
    ("seal", "a golden oriental seal stamp with red tassel, ornamental carved face, warm amber glow"),
    ("hour", "a golden hourglass with flowing amber sand, calm unhurried mood"),
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

for variant, subject in SUBJECTS:
    prompt = f"{subject}, {STYLE}"
    for seed in SEEDS:
        out = os.path.join(OUT, f"wealth_inseong_{variant}{seed}.png")
        if os.path.exists(out):
            print(f"  skip {variant}{seed}", flush=True); continue
        ts = time.time()
        img = pipe(prompt=prompt, width=W, height=H, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  inseong_{variant}{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s", flush=True)
