# -*- coding: utf-8 -*-
"""12띠 입벌림 일관 톤다운 — 과도한 분홍/혀·기괴함 제거(보이는 개구는 유지). anti-grotesque 네거티브."""
import os, sys, time
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from PIL import Image, ImageDraw, ImageFilter
from diffusers import StableDiffusionXLInpaintPipeline
MODEL = r"C:\shorts\models\stable-diffusion-xl-base-1.0"
LIB = r"D:\saju_agent\backend\app\services\assets\video_stills"
W, H = 768, 1344
ANIMAL = {"쥐":"mouse","소":"ox","호랑이":"tiger","토끼":"rabbit","용":"dragon",
          "말":"horse","양":"sheep","원숭이":"monkey","닭":"rooster","개":"dog","돼지":"pig"}  # 뱀=이미 수정됨, 제외
CY = {"초년":0.42, "유년":0.40, "청년":0.56, "장년":0.56, "노년":0.56}
NEG = ("grotesque, deformed, scary, gaping wide open mouth, sharp fangs, long sticking out tongue, "
       "excessive pink, bright pink mouth, melted, distorted, extra teeth, horror, ugly, drooling")
t0 = time.time()
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_model_cpu_offload(gpu_id=0)
print(f"load {time.time()-t0:.0f}s", flush=True)
for zod, animal in ANIMAL.items():
    for stage, cyf in CY.items():
        base = Image.open(os.path.join(LIB, f"{zod}_{stage}.png")).convert("RGB").resize((W, H))
        mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
        cx, cy, rx, ry = int(W*0.5), int(H*cyf), int(W*0.135), int(H*0.06)
        md.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(9))
        out = pipe(prompt=f"cute friendly 3d pixar {animal} with mouth open speaking naturally, soft gentle smile, expressive, same character, high quality",
                   negative_prompt=NEG, image=base, mask_image=mask, strength=0.8, guidance_scale=7.0, num_inference_steps=30,
                   generator=torch.Generator("cpu").manual_seed(21)).images[0].resize((W, H))
        out.save(os.path.join(LIB, f"{zod}_{stage}_open.png"))
    print(f"  {zod} 입벌림 톤다운 ({time.time()-t0:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s", flush=True)
