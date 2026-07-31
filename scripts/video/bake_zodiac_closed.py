# -*- coding: utf-8 -*-
"""12띠 × 5단계(초년/유년/청년/장년/노년) '닫힌' 캐릭터 스틸 베이크(FLUX schnell, 고품질).
생애 나이순: 초년(아기)→유년(어린이)→청년→장년→노년.
검증용으로 D:\\saju_agent\\image\\{띠}\\{단계}.png 분리 저장. 통과분만 라이브러리로 복사."""
import os, time, sys
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from diffusers import FluxPipeline

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT_ROOT = r"D:\saju_agent\image"
os.makedirs(OUT_ROOT, exist_ok=True)

# 띠 → 영문 동물(12지)
ANIMAL = {
    "쥐": "cute mouse", "소": "ox", "호랑이": "tiger", "토끼": "rabbit", "용": "oriental dragon",
    "뱀": "snake", "말": "horse", "양": "sheep", "원숭이": "monkey", "닭": "rooster", "개": "dog", "돼지": "pig",
}
# 생애 5단계: 개성 + 프레이밍 + seed. 초년=아기(전신), 유년=어린이, 청년/장년/노년=머리어깨(손없음)
STAGE = {
    "초년":  ("cute adorable newborn baby {a} cub, very chubby, huge sparkly innocent eyes, tiny, sitting full body, joyful", 7),
    "유년":  ("cute little child {a} kid, playful cheerful, bright curious eyes, youthful small, head and shoulders portrait, no hands", 21),
    "청년":  ("confident young adult {a}, proud determined bright eyes, robust noble, head and shoulders portrait, no hands", 42),
    "장년":  ("dignified mature middle-aged {a}, calm wise authoritative composed, head and shoulders portrait, no hands", 77),
    "노년":  ("gentle serene elderly old {a}, soft kind warm eyes, grey-streaked fur, wise aged, head and shoulders portrait, no hands", 77),
}
BASE = ("anthropomorphic {a}, 3D Pixar animation movie character, highly detailed expressive face, "
        "beautiful polished render, Korean hanbok, clean soft studio background, cinematic lighting, sharp high quality")

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try: pipe.vae.enable_tiling()
except Exception: pass
print(f"load {time.time()-t0:.0f}s", flush=True)

for zod, animal in ANIMAL.items():
    zdir = os.path.join(OUT_ROOT, zod); os.makedirs(zdir, exist_ok=True)
    for stage, (pers, seed) in STAGE.items():
        ts = time.time()
        prompt = f"{pers.format(a=animal)}, {BASE.format(a=animal)}"
        img = pipe(prompt=prompt, width=768, height=1344, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(os.path.join(zdir, f"{stage}.png"))
        print(f"  {zod}/{stage} ({time.time()-ts:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s ({len(ANIMAL)*len(STAGE)}장) -> {OUT_ROOT}", flush=True)
