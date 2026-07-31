# -*- coding: utf-8 -*-
"""O(오므림) 비세메만 '작고 부드러운 오므림'으로 재베이크 — 동물 주둥이가 이상해 보이지 않게.
낮은 strength + 작은 마스크 → 닫힘에 가깝되 살짝 오므린 안전한 모양. TEST=True면 후보 비교만."""
import os, sys, time
os.environ["CUDA_VISIBLE_DEVICES"] = "1"; sys.stdout.reconfigure(encoding="utf-8")  # 사주 자원=GPU1
import torch
from PIL import Image, ImageDraw, ImageFilter
from diffusers import StableDiffusionXLInpaintPipeline
MODEL = r"C:\shorts\models\stable-diffusion-xl-base-1.0"
LIB = r"D:\saju_agent\backend\app\services\assets\video_stills"
SCR = r"C:\Users\orion\AppData\Local\Temp\claude\D--saju-agent\931184cc-74b4-4e63-811a-16dabf38246e\scratchpad"
W, H = 768, 1344
ANIMAL = {"쥐":"mouse","소":"ox","호랑이":"tiger","토끼":"rabbit","용":"dragon","뱀":"snake",
          "말":"horse","양":"sheep","원숭이":"monkey","닭":"rooster","개":"dog","돼지":"pig"}
CY = {"초년":0.42, "유년":0.40, "청년":0.57, "장년":0.57, "노년":0.57}
TEST = (len(sys.argv) > 1 and sys.argv[1] == "test")
ZODIACS = ["호랑이","돼지","말"] if TEST else list(ANIMAL.keys())
STAGES = ["청년"] if TEST else list(CY.keys())
# 부드러운 오므림: 입을 살짝만 작게 오므림. wide/gape 금지.
PRM = "cute 3d pixar {a} face, mouth softly rounded into a small gentle 'o' shape, lips slightly pursed, mouth only a little open, calm subtle natural expression, same character, high quality"
NEG = "wide open mouth, gaping, jaw dropped, big open mouth, teeth bared, screaming, grotesque, deformed, scary, melted, distorted, double mouth, horror, ugly"
t0 = time.time()
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_model_cpu_offload(gpu_id=0)  # CUDA_VISIBLE_DEVICES=1 마스킹→gpu_id0=물리GPU1
print(f"load {time.time()-t0:.0f}s", flush=True)
for zod in ZODIACS:
    a = ANIMAL[zod]
    for stage in STAGES:
        cyf = CY[stage]
        base = Image.open(os.path.join(LIB, f"{zod}_{stage}.png")).convert("RGB").resize((W, H))
        mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
        cx, cy, rx, ry = int(W*0.5), int(H*cyf), int(W*0.105), int(H*0.052)  # 작은 마스크
        md.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(7))
        out = pipe(prompt=PRM.format(a=a), negative_prompt=NEG, image=base, mask_image=mask,
                   strength=0.6, guidance_scale=7.0, num_inference_steps=30,
                   generator=torch.Generator("cpu").manual_seed(11)).images[0].resize((W, H))
        if TEST:
            out.save(f"{SCR}/Otest_{zod}.png")
        else:
            out.save(os.path.join(LIB, f"{zod}_{stage}_O.png"))
        print(f"  {zod}/{stage} O ({time.time()-t0:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s", flush=True)
