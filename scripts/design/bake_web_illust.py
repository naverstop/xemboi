# -*- coding: utf-8 -*-
"""웹 랜딩 6대 기능 카드 + 히어로 일러스트 베이크 (FLUX schnell, 1회성 오프라인).
scripts/video/bake_zodiac_closed.py 와 동일 파이프라인 — 기존 12띠 에셋과 스타일 통일(3D 캐릭터·한복).
후보를 D:\\saju_agent\\image\\web_illust\\{key}\\seed{n}.png 로 저장, 선별분만 frontend/public/features/ 에 webp 배치.

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
os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # 1회성 베이크: 유휴 GPU0 사용(GPU1=LLM 서빙 회피)

import torch
from diffusers import FluxPipeline

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT_ROOT = r"D:\saju_agent\image\web_illust"
os.makedirs(OUT_ROOT, exist_ok=True)

# 기존 12띠 에셋과 동일한 스타일 앵커(bake_zodiac_closed.py BASE) + 브랜드 파랑·금 라이팅
BASE = ("3D Pixar animation movie style, highly detailed, beautiful polished render, "
        "Korean traditional hanbok clothing, soft azure blue and warm gold color palette, "
        "clean soft studio background with gentle glow, cinematic lighting, sharp high quality")

# 6대 기능 카드(FeatImg 키와 1:1) + 히어로 — 카드는 가로형
THEMES = {
    "sang":      "wise dignified anthropomorphic tiger scholar in hanbok reading a glowing celestial birth chart scroll "
                 "with hanja symbols floating around, warm thoughtful expression, waist-up",
    "gunghap":   "adorable anthropomorphic rabbit and dog couple in hanbok facing each other under a glowing heart-shaped "
                 "paper lantern, tender warm mood, romantic soft pink and blue glow",
    "taekil":    "cheerful anthropomorphic rooster in hanbok pointing at a traditional korean lunar calendar, "
                 "full moon and auspicious clouds in background, festive confident mood",
    "jakmyeong": "focused anthropomorphic monkey calligrapher in hanbok writing elegant hanja characters with a large "
                 "ink brush on hanji paper, ink stone beside, serene concentration",
    "gaemyeong": "confident anthropomorphic horse in hanbok holding two name plaques, one old faded and one new glowing, "
                 "transformation theme, hopeful bright mood",
    "aho":       "noble anthropomorphic azure dragon in scholarly hanbok stamping a red seal onto calligraphy artwork, "
                 "artist studio with brushes and scrolls, dignified refined mood",
    "hero":      "majestic night sky filled with constellations and a large glowing full moon, tiny cute anthropomorphic "
                 "zodiac animal characters in hanbok gazing up from a traditional korean pavilion silhouette, "
                 "deep blue starry atmosphere with gold star accents, wide panoramic dreamy scene",
}
SEEDS = [7, 21, 42, 77]
SIZE = {"hero": (1344, 768)}  # 카드 기본 1088×672(가로), 히어로는 와이드
DEFAULT_SIZE = (1088, 672)

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"load {time.time()-t0:.0f}s", flush=True)

for key, theme in THEMES.items():
    kdir = os.path.join(OUT_ROOT, key)
    os.makedirs(kdir, exist_ok=True)
    w, h = SIZE.get(key, DEFAULT_SIZE)
    for seed in SEEDS:
        out = os.path.join(kdir, f"seed{seed}.png")
        if os.path.exists(out):
            print(f"  skip {key}/seed{seed}", flush=True)
            continue
        ts = time.time()
        prompt = f"{theme}, {BASE}"
        img = pipe(prompt=prompt, width=w, height=h, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  {key}/seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s ({len(THEMES)*len(SEEDS)}장) -> {OUT_ROOT}", flush=True)
