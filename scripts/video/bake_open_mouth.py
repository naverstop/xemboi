# -*- coding: utf-8 -*-
"""12띠 × 5단계 '입벌림' 버전(SDXL 인페인팅) — 말하기 flap 재료.
단계별 입 세로위치(CY): 초년/유년=전신(입 위쪽), 청년/장년/노년=머리어깨(입 가운데아래).
{띠}/{단계}_open.png 로 저장. 생성 후 전수 검증, 빗나간 건 CY 조정 재생성."""
import os, time, sys
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from PIL import Image, ImageDraw, ImageFilter
from diffusers import StableDiffusionXLInpaintPipeline
MODEL = r"C:\shorts\models\stable-diffusion-xl-base-1.0"
ROOT = r"D:\saju_agent\image"
W, H = 768, 1344
ANIMAL = {"쥐":"mouse","소":"ox","호랑이":"tiger","토끼":"rabbit","용":"dragon","뱀":"snake",
          "말":"horse","양":"sheep","원숭이":"monkey","닭":"rooster","개":"dog","돼지":"pig"}
# 단계별 입 세로위치(프레임 비율). 이번엔 초년/유년만 재생성(chibi 전신=머리커서 입 위쪽)
# 청년/장년/노년(머리어깨 0.57)은 이미 양호 → 건드리지 않음
CY = {"초년":0.42, "유년":0.40}

t0 = time.time()
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_model_cpu_offload(gpu_id=0)
print(f"load {time.time()-t0:.0f}s", flush=True)
for zod, animal in ANIMAL.items():
    for stage, cyf in CY.items():
        src_p = os.path.join(ROOT, zod, f"{stage}.png")
        if not os.path.exists(src_p): print(f"  SKIP {zod}/{stage}(없음)", flush=True); continue
        base = Image.open(src_p).convert("RGB").resize((W, H))
        mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
        cx, cy, rx, ry = int(W*0.5), int(H*cyf), int(W*0.155), int(H*0.072)
        md.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(8))
        out = pipe(prompt=f"3d pixar {animal} with mouth open talking, jaw open showing teeth and pink tongue, expressive, same character",
                   negative_prompt="closed mouth, blurry, deformed, ugly, human",
                   image=base, mask_image=mask, strength=0.99, guidance_scale=7.5, num_inference_steps=28,
                   generator=torch.Generator("cpu").manual_seed(5)).images[0].resize((W, H))
        out.save(os.path.join(ROOT, zod, f"{stage}_open.png"))
    print(f"  {zod} 입벌림 5단계 ({time.time()-t0:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s (60장)", flush=True)
