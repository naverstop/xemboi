# -*- coding: utf-8 -*-
"""B-4 부적(符籍) 배경 문양 베이크 (FLUX schnell, 1회성 오프라인).

목적 6종 × 시드 2개 = 12장. 주사(朱砂) 붉은 선묘 × 황지(黃紙) 전통 부적 양식의
'가운데가 빈' 세로 문양 — 부적명 한자·간지·발행일·관인은 PIL이 결정적으로 각인한다.
후보: image/amulet_bg/{purpose}_seed{n}.png → 선별본을 backend/app/services/assets/amulet_{purpose}.jpg 로.

주의: GPU0(쇼츠 자원) 유휴 시에만 실행 — VRAM 게이트(8GB)로 자동 중단. GPU1은 LLM 서빙 중이라 사용 금지.
실행: C:\\shorts\\.venv\\Scripts\\python.exe scripts/design/bake_amulet_bg.py
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
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import torch
from diffusers import FluxPipeline

MODEL = r"C:\shorts\models\flux-black-forest-labs-FLUX.1-schnell"
OUT = r"D:\saju_agent\image\amulet_bg"
os.makedirs(OUT, exist_ok=True)

BASE = ("traditional korean bujeok talisman sheet, vermilion cinnabar red ink linework on aged "
        "golden-yellow hanji mulberry paper, intricate symmetrical talismanic ornament border frame, "
        "{motif}, folk shamanic spiritual art style, tall vertical composition, large empty blank "
        "center panel reserved for calligraphy, clean edges, flat top-down view, "
        "no text, no letters, no characters, no writing, no watermark")

PURPOSES = {
    "wealth":  "swirling auspicious clouds and stacked round coin motifs in the border",
    "love":    "pair of mandarin ducks and blooming peony flowers woven into the border",
    "exam":    "a crane rising over scroll and brush motifs in the border",
    "health":  "turtle shell patterns and pine branch motifs of longevity in the border",
    "protect": "fierce guardian tiger face at the top and thunder spiral patterns in the border",
    "biz":     "rising sun over mountains and phoenix wing motifs in the border",
}
SEEDS = [7, 42]
W_, H_ = 768, 1408  # 부적 세로비(~1:1.83), 16의 배수

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"load {time.time()-t0:.0f}s", flush=True)

for key, motif in PURPOSES.items():
    for seed in SEEDS:
        out = os.path.join(OUT, f"{key}_seed{seed}.png")
        if os.path.exists(out):
            print(f"  skip {key}_seed{seed}", flush=True)
            continue
        ts = time.time()
        img = pipe(prompt=BASE.format(motif=motif), width=W_, height=H_, num_inference_steps=4,
                   guidance_scale=0.0, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  {key}_seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s -> {OUT}", flush=True)
