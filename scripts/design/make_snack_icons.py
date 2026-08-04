# -*- coding: utf-8 -*-
"""무료 테스트(스낵) 결과 아이콘 11종 베이크 (FLUX schnell, 1회성 오프라인).

기존엔 결과마다 이모지(🎲/✨…)를 원형에 얹어 싸구려로 보였다(운영자 지적).
결과 '캐릭터'(성향)를 상징으로 담은 프리미엄 엠블럼으로 교체한다.

통일 규칙 — 11종이 한 세트로 읽히도록 스타일 문구를 공유하고 소재만 성향별로 다르게:
  · 원형 메달리온 구도(현 UI가 원형 배지) · 중앙 정렬 · 금박 라인워크
  · 따뜻한 아이보리 배경(밝은 카드 위에 얹힘) · 타입 고유색을 주조색으로
  · 글자 금지(라벨은 CSS/PIL 합성)

GPU0(쇼츠) 유휴 시에만: VRAM 게이트로 자동 중단. GPU1=LLM 은 미사용.
출력: D:\\saju_agent\\image\\snack_icons\\{key}_seed{n}.png
실행: C:/shorts/.venv/Scripts/python.exe scripts/design/make_snack_icons.py
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
OUT = r"D:\saju_agent\image\snack_icons"
os.makedirs(OUT, exist_ok=True)

# 전 종목 공통 스타일 — 한 세트로 보이게 고정(소재만 교체)
STYLE = ("luxurious circular medallion emblem, perfectly centered composition, "
         "polished 3D gold metal filigree linework, glossy jewel enamel inlay, "
         "ornate elegant ring border, soft radiant glow, warm ivory background, "
         "korean traditional-modern fusion, ultra detailed, premium render, "
         "no text, no letters, no words, no numbers")

# (key, 주제 묘사) — 결과 '성향'을 상징으로. 색은 타입 고유색을 주조로.
SUBJECTS = [
    # ── 재물(財) 6유형 ──
    ("wealth_pyeonjae",                                     # 과감한 승부사형 #c0392b
     "a pair of elegant golden dice caught mid-roll with dynamic motion trails and sparks, "
     "bold crimson red and rich gold, daring fortune"),
    ("wealth_jeongjae",                                     # 차곡차곡 자산가형 #2e7d32
     "neatly stacked golden coins growing into a flourishing jade money tree with round leaves, "
     "deep emerald green and gold, steady abundance"),
    ("wealth_siksang",                                      # 만들어내는 재주꾼형 #0496d8
     "an artisan's golden brush and palette with glowing creative swirls forming shapes, "
     "bright azure blue and gold, inventive craft"),
    ("wealth_bigyeop",                                      # 함께 크는 협업가형 #8a5cc0
     "two graceful golden hands clasping over a luminous orb with interlocking rings, "
     "rich violet purple and gold, partnership and trust"),
    ("wealth_inseong",                                      # 느긋한 관리형 #b8860b
     "an open golden ledger book beside a serene scholar's oil lamp with calm light, "
     "warm amber and antique gold, unhurried wisdom"),
    ("wealth_gwanseong",                                    # 반듯한 리더형 #3f5b8a
     "a stately golden classical pillar with perfectly balanced scales of justice, "
     "deep navy blue and gold, integrity and leadership"),
    # ── 도화(桃花) 5등급 ──
    ("dohwa_classic",                                       # 은은한 클래식 매력 #6b8cae
     "a graceful white crane standing among soft moonlit clouds, "
     "muted slate blue and silver with gold accents, quiet timeless elegance"),
    ("dohwa_cozy",                                          # 편안한 매력 #c08a4a
     "a warm ceramic teacup with gentle curling steam and small blossoms, "
     "soft amber and cream with gold rim, inviting comfort"),
    ("dohwa_spark",                                         # 은근히 눈길을 끄는 매력 #c0518a
     "a single peach blossom with softly drifting glowing sparkles around it, "
     "rose pink and gold, subtle magnetic allure"),
    ("dohwa_magnetic",                                      # 치명적인 도화 매력 #c0392b
     "a deep crimson rose in full bloom with velvet petals and glowing embers, "
     "vivid crimson and gold, irresistible charm"),
    ("dohwa_star",                                          # 타고난 스타 오라 #b8860b
     "a radiant golden star crowned with a delicate tiara and shimmering aura rays, "
     "brilliant gold and champagne, born star presence"),
]

SEEDS = [7, 42]      # 종목당 2안 → 좋은 쪽 채택
W = H = 1024

t0 = time.time()
pipe = FluxPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, use_safetensors=True, local_files_only=True)
pipe.enable_sequential_cpu_offload(gpu_id=0)
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"load {time.time()-t0:.0f}s", flush=True)

total = len(SUBJECTS) * len(SEEDS)
done = 0
for key, subject in SUBJECTS:
    prompt = f"{subject}, {STYLE}"
    for seed in SEEDS:
        out = os.path.join(OUT, f"{key}_seed{seed}.png")
        done += 1
        if os.path.exists(out):
            print(f"  [{done}/{total}] skip {key}_seed{seed}", flush=True); continue
        ts = time.time()
        img = pipe(prompt=prompt, width=W, height=H, num_inference_steps=4, guidance_scale=0.0,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        img.save(out)
        print(f"  [{done}/{total}] {key}_seed{seed} ({time.time()-ts:.0f}s)", flush=True)

print(f"done {time.time()-t0:.0f}s -> {OUT}", flush=True)
