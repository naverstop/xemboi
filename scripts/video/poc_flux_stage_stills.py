# -*- coding: utf-8 -*-
"""성년 호랑이 후보 재생성(고품질·손 미노출 head&shoulders). 후보 2개씩 → 직접 보고 선택."""
import os, time, sys
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from diffusers import FluxPipeline
MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
SCR = r"C:\Users\orion\AppData\Local\Temp\claude\D--saju-agent\931184cc-74b4-4e63-811a-16dabf38246e\scratchpad\cand"
os.makedirs(SCR, exist_ok=True)
# 손/발 미노출(head&shoulders) + 고품질 디테일 강조
BASE = ("anthropomorphic tiger, 3D Pixar animation movie character, highly detailed expressive face, "
        "beautiful polished render, orange fur with crisp black stripes, Korean hanbok collar, "
        "head and shoulders portrait, centered, no hands, clean soft studio background, cinematic lighting, sharp high quality")
STAGES = {
    "청년": "confident young adult tiger, proud determined bright eyes, robust noble",
    "중년": "dignified mature middle-aged tiger, calm wise authoritative composed",
    "노년": "gentle serene elderly tiger, soft kind warm eyes, grey-streaked fur, wise",
    "마무리": "peaceful hopeful elderly tiger, warm gentle smile, grey fur, content",
}
t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try: pipe.vae.enable_tiling()
except Exception: pass
print(f"load {time.time()-t0:.0f}s", flush=True)
for st, pers in STAGES.items():
    for seed in (42, 77):
        ts = time.time()
        img = pipe(prompt=f"{pers}, {BASE}", width=768, height=1344, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(os.path.join(SCR, f"{st}_{seed}.png"))
        print(f"  {st}_{seed}: {time.time()-ts:.0f}s", flush=True)
print(f"done {time.time()-t0:.0f}s", flush=True)
