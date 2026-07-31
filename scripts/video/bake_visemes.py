# -*- coding: utf-8 -*-
"""비세메 입모양(A크게/O오므림/E옆으로) 베이크 — 모음별 립싱크용. 닫힘=기존 스틸.
ZODIACS 리스트로 대상 띠 지정(토끼 먼저 검증 후 전체)."""
import os, sys, time
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # 사주 자원=GPU1(GPU0은 타 서비스). 마스킹돼 gpu_id=0이 곧 GPU1; sys.stdout.reconfigure(encoding="utf-8")
import torch
from PIL import Image, ImageDraw, ImageFilter
from diffusers import StableDiffusionXLInpaintPipeline
MODEL = r"C:\shorts\models\stable-diffusion-xl-base-1.0"
LIB = r"D:\saju_agent\backend\app\services\assets\video_stills"
W, H = 768, 1344
ANIMAL = {"쥐":"mouse","소":"ox","호랑이":"tiger","토끼":"rabbit","용":"dragon","뱀":"snake",
          "말":"horse","양":"sheep","원숭이":"monkey","닭":"rooster","개":"dog","돼지":"pig"}
ZODIACS = ["쥐", "소", "호랑이", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]   # 토끼=완료
CY = {"초년":0.42, "유년":0.40, "청년":0.57, "장년":0.57, "노년":0.57}
def vp(a):
    return {
      "A": f"cute 3d pixar {a} face with mouth wide open, jaw dropped down, saying 'ah', open round mouth",
      "O": f"cute 3d pixar {a} face with lips rounded and pushed forward in small O shape, saying 'oh', puckered",
      "E": f"cute 3d pixar {a} face with mouth slightly open and lips spread wide, saying 'ee', showing front teeth",
    }
NEG = "grotesque, deformed, scary, melted, distorted, extra teeth, ugly, double mouth, horror, gaping"
t0 = time.time()
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_model_cpu_offload(gpu_id=0)
print(f"load {time.time()-t0:.0f}s", flush=True)
for zod in ZODIACS:
    a = ANIMAL[zod]
    for stage, cyf in CY.items():
        base = Image.open(os.path.join(LIB, f"{zod}_{stage}.png")).convert("RGB").resize((W, H))
        mask = Image.new("L", (W, H), 0); md = ImageDraw.Draw(mask)
        cx, cy, rx, ry = int(W*0.5), int(H*cyf), int(W*0.14), int(H*0.072)
        md.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(8))
        for k, prm in vp(a).items():
            out = pipe(prompt=f"{prm}, same character, high quality", negative_prompt=NEG, image=base, mask_image=mask,
                       strength=0.85, guidance_scale=7.5, num_inference_steps=28,
                       generator=torch.Generator("cpu").manual_seed(7)).images[0].resize((W, H))
            out.save(os.path.join(LIB, f"{zod}_{stage}_{k}.png"))
        print(f"  {zod}/{stage} A/O/E ({time.time()-t0:.0f}s)", flush=True)
print(f"done {time.time()-t0:.0f}s", flush=True)
