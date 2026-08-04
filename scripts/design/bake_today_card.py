# -*- coding: utf-8 -*-
"""오늘의 운세(B-2) 랜딩 카드 일러스트 베이크 — 4개 컨셉안 × 2시드 (FLUX schnell, 1회성).

컨셉(운영자 요청 '의미가 맞고 있어보이는' 4안, 기존 12띠·기능카드와 스타일 통일):
  A magpie   — 한복 까치가 한옥 일출 위에서 좋은 소식 알림(민속: 아침 까치=길보)
  B sunchar  — 구름 위로 떠오르는 귀여운 아기 해님 캐릭터 + 행운 동전
  C calcat   — 한복 고양이가 아침 햇살 속 일일 달력(일력)을 넘김
  D haetae   — 아기 해태가 나침반·오색 비단 리본과 아침 해 맞이(행운 색·방위)

주의: GPU0(쇼츠 자원) 유휴 시에만 — VRAM 게이트(8GB). GPU1은 LLM 서빙이라 사용 금지.
선별분은 convert 규격(880px q85 JPEG)으로 frontend/public/features/today.jpg 배치.
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
OUT = r"D:\saju_agent\image\web_illust\today"
os.makedirs(OUT, exist_ok=True)

# 기존 카드와 동일 스타일 앵커(bake_web_illust.py BASE)
BASE = ("3D Pixar animation movie style, highly detailed, beautiful polished render, "
        "Korean traditional hanbok clothing, soft azure blue and warm gold color palette, "
        "clean soft background with gentle glow, cinematic lighting, sharp high quality")

THEMES = {
    "A_magpie": "one adorable anthropomorphic korean magpie bird in hanbok perched on a traditional "
                "hanok rooftop at golden sunrise, joyfully announcing good news, tiny letter scroll in wing, "
                "soft morning mist, hopeful warm mood",
    "B_sunchar": "one adorable chubby baby sun character with cute smiling face and big sparkling eyes "
                 "rising above soft fluffy clouds, tiny hanok village silhouette below, small golden lucky "
                 "coins floating, fresh morning energy",
    "C_calcat": "one adorable cat in hanbok flipping a page of a traditional daily calendar on a cozy desk, "
                "warm morning sunbeam through window, small teacup with steam, peaceful start of the day",
    "D_haetae": "one adorable baby haetae korean mythical guardian creature with soft fur greeting the "
                "golden morning sun, ornate small compass and flowing five-color silk ribbons around, "
                "auspicious lucky morning mood",
}

pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)

for key, theme in THEMES.items():
    for seed in (7, 42):
        out = os.path.join(OUT, f"{key}_seed{seed}.png")
        if os.path.exists(out):
            continue
        t = time.time()
        img = pipe(prompt=f"{theme}, {BASE}", width=1088, height=672, num_inference_steps=4,
                   guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"{key} seed{seed} ({time.time()-t:.0f}s)", flush=True)
print("done", flush=True)
