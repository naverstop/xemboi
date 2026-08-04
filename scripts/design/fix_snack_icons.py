# -*- coding: utf-8 -*-
"""스낵 아이콘 재생성 — 1차에서 탈락한 2종(재주꾼·관리형).

1차 실패 원인: 프롬프트가 CLIP 77토큰을 넘겨 꼬리의 'no text, no letters'가 잘렸고,
그 결과 메달리온 중앙에 정체불명 한자 글리프가 생성됨(재주꾼), 원형 구도도 이탈(관리형).
대책: 스타일 문구를 대폭 압축하고 'no text'를 앞쪽에 배치해 절대 잘리지 않게 한다.

출력: D:\\saju_agent\\image\\snack_icons\\{key}_fix{seed}.png
실행: C:/shorts/.venv/Scripts/python.exe scripts/design/fix_snack_icons.py
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

# 압축 스타일(≈20토큰) — 'no text' 를 앞에 둬 잘림 방지
STYLE = "no text, circular gold medallion emblem, centered, gold filigree, enamel inlay, ivory background, premium 3d render"

SUBJECTS = [
    ("wealth_siksang",   # 만들어내는 재주꾼형 #0496d8
     "a golden artisan paintbrush crossed with a palette, swirling azure blue creative energy"),
    ("wealth_inseong",   # 느긋한 관리형 #b8860b
     "a golden open book and a small glowing oil lamp, calm amber light"),
]

SEEDS = [11, 23, 42]   # 3안씩 — 확실히 쓸만한 게 나오도록
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
        out = os.path.join(OUT, f"{key}_fix{seed}.png")
        if os.path.exists(out):
            print(f"  skip {key}_fix{seed}", flush=True); continue
        ts = time.time()
        img = pipe(prompt=prompt, width=W, height=H, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  {key}_fix{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s -> {OUT}", flush=True)
