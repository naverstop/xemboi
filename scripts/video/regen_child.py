# -*- coding: utf-8 -*-
"""유년(어린이) 단계가 '사람 아이'로 나온 띠 재생성 — 동물 토큰 강하게 앞세움(사람화 방지)."""
import os, time, sys
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from diffusers import FluxPipeline
MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT_ROOT = r"D:\saju_agent\image"
ANIMAL = {"쥐":"mouse","소":"ox","호랑이":"tiger","토끼":"rabbit","용":"dragon","뱀":"snake",
          "말":"horse","양":"sheep","원숭이":"monkey","닭":"rooster chicken","개":"dog","돼지":"pig"}
SEED = 99
# 동물 토큰을 앞·중·뒤로 반복, child/kid/boy 단어 배제(사람화 차단)
def prompt(a):
    return (f"chibi baby {a}, juvenile young {a} cub, small cute {a} with full {a} head and {a} face and {a} features, "
            f"big round head kawaii, anthropomorphic {a} animal character (not human), wearing Korean hanbok, "
            f"3D Pixar animation render, highly detailed, clean soft studio background, head and shoulders, no hands")
t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try: pipe.vae.enable_tiling()
except Exception: pass
print(f"load {time.time()-t0:.0f}s", flush=True)
for zod, animal in ANIMAL.items():
    ts = time.time()
    img = pipe(prompt=prompt(animal), width=768, height=1344, num_inference_steps=4, guidance_scale=0.0,
               generator=torch.Generator("cpu").manual_seed(SEED)).images[0]
    img.save(os.path.join(OUT_ROOT, zod, "유년.png"))
    print(f"  {zod}/유년 재생성 ({time.time()-ts:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s", flush=True)
