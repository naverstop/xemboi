# -*- coding: utf-8 -*-
"""작명 '누구의 이름인가요?' 선택 아이콘 2종 베이크 (FLUX schnell, 1회성).
  · 아기 이름 짓기  → naming_baby.webp
  · 내 이름 짓기    → naming_self.webp
기존 메뉴 아이콘(bake_partner_icon.py)과 동일 스타일: 금+사파이어 원형 메달리온.
주의: GPU0 유휴 시에만(VRAM 게이트 8GB). GPU1은 LLM 서빙 — 사용 금지.
실행: C:/shorts/.venv/Scripts/python.exe scripts/design/bake_naming_subject_icons.py
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
from PIL import Image, ImageDraw

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
RAW = r"D:\saju_agent\image\menu_icons\naming_subject"
DEST = r"D:\saju_agent\frontend\public\icons\menu"
os.makedirs(RAW, exist_ok=True)

# ⚠️ CLIP 77토큰 — 'no text'를 앞에 두고 프롬프트를 짧게(꼬리 잘림 방지, 운영자 보고 버그 교훈).
# 메달리온 스타일은 사진 인물 + 가짜 한자 부작용 → 무료테스트에서 호평받은 캐릭터 일러스트로 전환.
BASE = ("cute 3d character illustration, soft rounded pixar style, glossy, warm cinematic lighting, "
        "centered on soft pastel gradient circle, app icon, ultra detailed, high quality")
ITEMS = [
    ("naming_baby", (11, 23, 7), "no text, adorable chubby smiling baby wrapped in a soft blanket, warm pink pastel"),
    ("naming_self", (11, 23, 7), "no text, friendly cheerful young adult smiling and waving one hand, soft blue pastel"),
]

def finish(src: str, dest: str, size: int = 256):
    """원형 크롭 + 리사이즈 → 투명 배경 webp(메뉴 아이콘 규격)."""
    im = Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((2, 2, size - 2, size - 2), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    out.save(dest, "WEBP", quality=92, method=6)

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
for name, seeds, theme in ITEMS:
    for seed in seeds:
        raw = os.path.join(RAW, f"{name}_s{seed}.png")
        if not os.path.exists(raw):
            img = pipe(prompt=f"{theme}, {BASE}", width=768, height=768, num_inference_steps=4,
                       guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
            img.save(raw)
            print(f"{name} seed{seed} ({time.time()-t0:.0f}s)", flush=True)
print("생성 완료 — 후보 확인 후 finish()로 선별본을 webp로 저장하세요.", flush=True)
print(f"후보 폴더: {RAW}", flush=True)
