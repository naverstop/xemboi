# -*- coding: utf-8 -*-
"""뱀 입벌림 재생성 — 기괴함 방지(약한 strength + 뱀 친화 프롬프트 + anti-grotesque 네거티브)."""
import os, sys, time
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from PIL import Image, ImageDraw, ImageFilter
from diffusers import StableDiffusionXLInpaintPipeline
MODEL = r"C:\shorts\models\stable-diffusion-xl-base-1.0"
LIB = r"D:\saju_agent\backend\app\services\assets\video_stills"
W, H = 768, 1344
# 초년/유년=전신 chibi(입 위쪽), 청년/장년/노년=머리어깨
CY = {"초년": 0.42, "유년": 0.40, "청년": 0.55, "장년": 0.55, "노년": 0.55}
t0 = time.time()
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_model_cpu_offload(gpu_id=0)
print(f"load {time.time()-t0:.0f}s", flush=True)
for stage, cyf in CY.items():
    base = Image.open(os.path.join(LIB, f"뱀_{stage}.png")).convert("RGB").resize((W, H))
    mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
    cx, cy, rx, ry = int(W*0.5), int(H*cyf), int(W*0.13), int(H*0.055)   # 약간 작은 마스크
    md.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(10))
    out = pipe(prompt=f"cute friendly 3d pixar cartoon snake with mouth slightly open in a gentle smile, small soft tongue, adorable, same character, high quality",
               negative_prompt="grotesque, deformed, scary, gaping wide mouth, sharp fangs, melted, distorted, extra teeth, horror, ugly",
               image=base, mask_image=mask, strength=0.72, guidance_scale=7.0, num_inference_steps=30,
               generator=torch.Generator("cpu").manual_seed(13)).images[0].resize((W, H))
    out.save(os.path.join(LIB, f"뱀_{stage}_open.png"))
    print(f"  뱀_{stage}_open ({time.time()-t0:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s", flush=True)
