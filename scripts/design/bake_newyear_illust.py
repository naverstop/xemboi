# -*- coding: utf-8 -*-
"""B-1 신년운세 카드 일러스트 베이크 — bake_web_illust.py 와 동일 파이프라인(1회성)."""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
free = int(subprocess.check_output(["nvidia-smi","--query-gpu=memory.free","--format=csv,noheader,nounits","--id=0"]).decode().strip())
if free < 8000:
    print(f"abort: GPU0 free {free}MB", flush=True); sys.exit(1)
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
import torch
from diffusers import FluxPipeline
MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT = r"D:\saju_agent\image\web_illust\newyear"
os.makedirs(OUT, exist_ok=True)
BASE = ("3D Pixar animation movie style, highly detailed, beautiful polished render, "
        "Korean traditional hanbok clothing, soft azure blue and warm gold color palette, "
        "clean soft studio background with gentle glow, cinematic lighting, sharp high quality")
THEME = ("majestic red horse character in festive hanbok galloping toward a glowing golden sunrise "
         "over traditional korean rooftops, new year celebration mood, floating lucky pouches and "
         "sparkling lights, hopeful energetic atmosphere")
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
