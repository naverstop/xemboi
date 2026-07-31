# -*- coding: utf-8 -*-
"""비세메 립싱크 POC — 토끼 청년의 모음별 입모양(A/O/E) 생성. 닫힘=기존 스틸."""
import os, sys, time
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from PIL import Image, ImageDraw, ImageFilter
from diffusers import StableDiffusionXLInpaintPipeline
MODEL = r"C:\shorts\models\stable-diffusion-xl-base-1.0"
LIB = r"D:\saju_agent\backend\app\services\assets\video_stills"
SCR = r"C:\Users\orion\AppData\Local\Temp\claude\D--saju-agent\931184cc-74b4-4e63-811a-16dabf38246e\scratchpad\viseme"
os.makedirs(SCR, exist_ok=True)
W, H = 768, 1344
base = Image.open(os.path.join(LIB, "토끼_청년.png")).convert("RGB").resize((W, H))
mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
cx, cy, rx, ry = int(W*0.5), int(H*0.57), int(W*0.14), int(H*0.072)
md.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(8))
VIS = {
 "A": "rabbit face with mouth wide open, jaw dropped down, saying 'ah' vowel, open round mouth showing tongue",
 "O": "rabbit face with lips rounded and pushed forward into a small O shape, saying 'oh' vowel, puckered lips",
 "E": "rabbit face with mouth slightly open and lips spread wide horizontally, saying 'ee' vowel, showing front teeth",
}
NEG = "grotesque, deformed, scary, melted, distorted, extra teeth, ugly, double mouth, horror"
t0 = time.time()
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_model_cpu_offload(gpu_id=0)
print(f"load {time.time()-t0:.0f}s", flush=True)
for k, prm in VIS.items():
    out = pipe(prompt=f"cute 3d pixar {prm}, same character, high quality",
               negative_prompt=NEG, image=base, mask_image=mask, strength=0.85, guidance_scale=7.5,
               num_inference_steps=30, generator=torch.Generator("cpu").manual_seed(7)).images[0].resize((W, H))
    out.save(os.path.join(SCR, f"vis_{k}.png")); out.resize((240, 420)).save(os.path.join(SCR, f"s_{k}.png"))
    print(f"  viseme {k} ({time.time()-t0:.0f}s)", flush=True)
# 닫힘도 비교용 축소
Image.open(os.path.join(LIB, "토끼_청년.png")).resize((240, 420)).save(os.path.join(SCR, "s_closed.png"))
print("done", flush=True)
