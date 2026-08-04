# -*- coding: utf-8 -*-
"""정지 일러스트 → 2~4초 자연 모션 루프(webm) — SVD img2vid-xt (1회성, GPU0 유휴 시).
사용: python svd_animate_card.py <입력.png> <출력접두어>
출력: <접두어>.webm (핑퐁 루프, vp9) + <접두어>.jpg (poster)
"""
import os, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
src, prefix = sys.argv[1], sys.argv[2]
free = int(subprocess.check_output(["nvidia-smi","--query-gpu=memory.free","--format=csv,noheader,nounits","--id=0"]).decode().strip())
if free < 8000:
    print(f"abort: GPU0 free {free}MB", flush=True); sys.exit(1)
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
import torch
from PIL import Image
from diffusers import StableVideoDiffusionPipeline

MODEL = r"C:\shorts\models\models--stabilityai--stable-video-diffusion-img2vid-xt\snapshots\9e43909513c6714f1bc78bcb44d96e733cd242aa"
img = Image.open(src).convert("RGB")
# SVD 규격 1024x576 — cover crop
tw, th = 1024, 576
ratio = max(tw / img.width, th / img.height)
img2 = img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)
left, top = (img2.width - tw) // 2, (img2.height - th) // 2
img2 = img2.crop((left, top, left + tw, top + th))

pipe = StableVideoDiffusionPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
frames = pipe(img2, decode_chunk_size=4, num_frames=25, motion_bucket_id=90, noise_aug_strength=0.05,
              generator=torch.Generator("cpu").manual_seed(42)).frames[0]
tmp = prefix + "_frames"
os.makedirs(tmp, exist_ok=True)
# 핑퐁(정방향+역방향)으로 이음새 없는 루프
seq = frames + frames[-2:0:-1]
for i, f in enumerate(seq):
    f.save(os.path.join(tmp, f"f{i:03d}.png"))
img2.save(prefix + ".jpg", "JPEG", quality=85)
subprocess.run([
    "ffmpeg", "-y", "-framerate", "14", "-i", os.path.join(tmp, "f%03d.png"),
    "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-pix_fmt", "yuv420p", "-an", prefix + ".webm",
], check=True, capture_output=True)
print("done:", prefix + ".webm", os.path.getsize(prefix + ".webm") // 1024, "KB", flush=True)
