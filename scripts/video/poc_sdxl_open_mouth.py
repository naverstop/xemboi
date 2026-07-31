# -*- coding: utf-8 -*-
"""5단계 전부 SDXL 인페인팅으로 입 벌린 버전 생성(per-stage 입 위치). 닫힘↔열림 flap 재료."""
import os, time, sys
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from PIL import Image, ImageDraw, ImageFilter
from diffusers import StableDiffusionXLInpaintPipeline
MODEL = r"C:\shorts\models\stable-diffusion-xl-base-1.0"
LIB = r"D:\saju_agent\backend\app\services\assets\video_stills"
SCR = r"C:\Users\orion\AppData\Local\Temp\claude\D--saju-agent\931184cc-74b4-4e63-811a-16dabf38246e\scratchpad"
W, H = 768, 1344
# per-stage 입 세로위치(프레임 비율). cub=전신(낮음), 성년=머리어깨(가운데)
CY = {"노년": 0.585}  # 노년만 입 위치 더 내려 재보완
PROMPT = {
 "도입": "cute 3d pixar baby tiger cub, mouth wide open in happy smile, showing small teeth and pink tongue, talking",
 "청년": "3d pixar young adult tiger, mouth open speaking confidently, showing teeth, expressive",
 "중년": "3d pixar mature tiger, mouth open speaking, showing teeth, dignified expressive",
 "노년": "3d pixar elderly grey tiger, jaw dropped with mouth wide open, large clearly open mouth showing teeth and pink tongue, talking",
 "마무리": "3d pixar elderly tiger, mouth open in warm hopeful smile, showing teeth",
}
t0 = time.time()
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_model_cpu_offload(gpu_id=0)
print(f"load {time.time()-t0:.0f}s", flush=True)
for st, cyf in CY.items():
    base = Image.open(os.path.join(LIB, f"호랑이_{st}.png")).convert("RGB").resize((W, H))
    mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
    cx, cy, rx, ry = int(W*0.5), int(H*cyf), int(W*0.155), int(H*0.075)
    md.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(8))
    ov = base.copy(); ImageDraw.Draw(ov).ellipse([cx-rx,cy-ry,cx+rx,cy+ry], outline=(255,0,0), width=6); ov.resize((220,385)).save(f"{SCR}/maskpos_{st}.png")
    out = pipe(prompt=PROMPT[st]+", high quality render, same character", negative_prompt="closed mouth, blurry, deformed, ugly, extra teeth",
               image=base, mask_image=mask, strength=0.99, guidance_scale=7.5, num_inference_steps=30,
               generator=torch.Generator("cpu").manual_seed(11)).images[0].resize((W, H))
    out.save(os.path.join(LIB, f"호랑이_{st}_open.png")); out.resize((220,385)).save(f"{SCR}/open_{st}.png")
    print(f"  {st}_open ({time.time()-t0:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s", flush=True)
