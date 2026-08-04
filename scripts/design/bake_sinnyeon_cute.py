# -*- coding: utf-8 -*-
"""신년운세 카드 v2 — 기존 12띠 에셋과 같은 '귀여운 아기 캐릭터' 스타일로 재베이크."""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
free = int(subprocess.check_output(["nvidia-smi","--query-gpu=memory.free","--format=csv,noheader,nounits","--id=0"]).decode().strip())
if free < 8000:
    print(f"abort: GPU0 free {free}MB", flush=True); sys.exit(1)
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
import torch
from diffusers import FluxPipeline
MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT = r"D:\saju_agent\image\web_illust\sinnyeon_cute"
os.makedirs(OUT, exist_ok=True)
# 12띠 초년 에셋과 동일 스타일 문법: adorable baby + 3D Pixar + big sparkling eyes
BASE = ("3D Pixar animation movie style, highly detailed, beautiful polished render, "
        "big sparkling eyes, chubby adorable proportions, soft fur, "
        "clean soft studio background with gentle warm glow, cinematic lighting, sharp high quality")
THEME = ("one adorable baby red horse character wearing a tiny festive hanbok, joyfully prancing, "
         "golden sunrise glow behind, floating red lucky pouches and small lanterns around, "
         "new year celebration, cute and lovely")
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
for seed in (7, 21, 42, 77):
    out = os.path.join(OUT, f"seed{seed}.png")
    if os.path.exists(out): continue
    t = time.time()
    img = pipe(prompt=f"{THEME}, {BASE}", width=1088, height=672, num_inference_steps=4,
               guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    img.save(out)
    print(f"seed{seed} ({time.time()-t:.0f}s)", flush=True)
print("done", flush=True)
