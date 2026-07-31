"""Pluggable 비주얼 렌더러 — 장면 → 프레임 PNG(자막 포함).

code: 코드 그래픽(무드 그라데이션 + 띠/단계/오행 + 자막) — PoC 검증, OOM 없음, v1 기본.
flux: 사전 베이크된 'FLUX 3D룩' 스틸 라이브러리 사용(없으면 code로 graceful 폴백).
v2: 진짜 리깅 3D 클립. settings `shorts_renderer`로 선택. 부록 C-4(v1-rich).
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 무드별 그라데이션(상단→하단 RGB)
_MOOD = {
    "밝음": ((250, 180, 90), (120, 40, 10)),
    "차분": ((40, 120, 130), (10, 30, 50)),
    "희망": ((60, 110, 210), (10, 20, 60)),
    "회상": ((120, 80, 160), (30, 10, 50)),
}
_DEFAULT_GRAD = ((80, 80, 95), (20, 20, 28))

_FONT_CANDIDATES = [
    # 상업배포용 Noto(OFL) 우선 — repo 번들 위치 후보
    os.path.join(os.path.dirname(__file__), "..", "assets", "NotoSansKR-Regular.ttf"),
    r"D:\saju_agent\backend\app\services\assets\NotoSansKR-Regular.ttf",
    r"C:\Windows\Fonts\malgun.ttf",  # 폴백(시스템)
]


def _font_path() -> str:
    for p in _FONT_CANDIDATES:
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return r"C:\Windows\Fonts\malgun.ttf"


# 관인(「相談紙印」) — PDF 상담서와 동일 직인 재사용
_SEAL_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "seal.png")
_BRAND = "인생상담 친구"


def build_watermark_overlay(title: str, W: int, H: int, out_png: str, credit: str = "") -> str:
    """최종 4K 위에 고정 합성할 투명 오버레이 PNG 생성.

    - 상단 중앙: 영상 제목("{닉네임}님의 사주영상")
    - 우측 하단: 직인(관인) + 브랜드("인생상담 친구") 워터마크
    - 최하단 중앙: 출처 크레딧("ⓒ {credit}") — 제작/소유 표기
    줌/팬에 흔들리지 않도록 프레임이 아닌 '스케일 후 고정 오버레이'로 얹는다.
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fp = _font_path()

    # ── 상단 타이틀 ──
    if title:
        f_title = ImageFont.truetype(fp, int(W * 0.046))
        ty = int(H * 0.05)
        bb = d.textbbox((0, 0), title, font=f_title)
        tw = bb[2] - bb[0]
        pad = int(W * 0.03)
        d.rounded_rectangle(
            [W // 2 - tw // 2 - pad, ty - int(H * 0.012), W // 2 + tw // 2 + pad, ty + (bb[3] - bb[1]) + int(H * 0.012)],
            radius=int(W * 0.02), fill=(0, 0, 0, 110),
        )
        # 그림자 + 본문
        d.text((W // 2 + 2, ty + 2), title, font=f_title, fill=(0, 0, 0, 160), anchor="ma")
        d.text((W // 2, ty), title, font=f_title, fill=(255, 255, 255, 235), anchor="ma")

    # ── 우측 '세로' 워터마크(상→하): 직인 상단 + 브랜드 세로글자 ──
    # (요건: 인생상담친구가 캐릭터에 가려지지 않게 우측상단→우측하단 세로 배치)
    seal_sz = int(W * 0.11)
    seal_x = W - seal_sz - int(W * 0.022)
    seal_y = int(H * 0.085)
    try:
        seal = Image.open(_SEAL_PATH).convert("RGBA").resize((seal_sz, seal_sz))
        a = seal.split()[3].point(lambda v: int(v * 0.85))
        seal.putalpha(a)
        img.alpha_composite(seal, (seal_x, seal_y))
    except Exception:
        pass  # 직인 없으면 브랜드 세로글자만
    f_brand = ImageFont.truetype(fp, int(W * 0.034))
    cx = W - int(W * 0.06)
    y = seal_y + seal_sz + int(H * 0.016)
    for ch in _BRAND.replace(" ", ""):
        for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            d.text((cx + dx, y + dy), ch, font=f_brand, fill=(0, 0, 0, 200), anchor="mm")
        d.text((cx, y), ch, font=f_brand, fill=(255, 255, 255, 230), anchor="mm")
        y += int(W * 0.050)

    # ── 최하단 중앙: 출처 크레딧(작게, 반투명) ──
    if credit:
        f_credit = ImageFont.truetype(fp, int(W * 0.021))
        ctxt = f"ⓒ {credit}"
        cyc = int(H * 0.975)
        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            d.text((W // 2 + dx, cyc + dy), ctxt, font=f_credit, fill=(0, 0, 0, 150), anchor="mm")
        d.text((W // 2, cyc), ctxt, font=f_credit, fill=(255, 255, 255, 190), anchor="mm")

    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    img.save(out_png)
    return out_png


def _wrap(text: str, n: int = 16, max_lines: int = 3) -> str:
    out = []
    t = text
    while t and len(out) < max_lines:
        out.append(t[:n])
        t = t[n:]
    if t and out:
        out[-1] = out[-1][:-1] + "…"
    return "\n".join(out)


class CodeGraphicRenderer:
    name = "code"

    def render_scene(self, scene: dict, character: dict, W: int, H: int, out_png: str) -> str:
        c1, c2 = _MOOD.get(scene.get("mood", ""), _DEFAULT_GRAD)
        img = Image.new("RGB", (W, H))
        px = img.load()
        for y in range(H):
            r = y / H
            col = tuple(int(c1[k] + (c2[k] - c1[k]) * r) for k in range(3))
            for x in range(W):
                px[x, y] = col
        d = ImageDraw.Draw(img)
        fp = _font_path()
        f_stage = ImageFont.truetype(fp, int(W * 0.045))
        f_zod = ImageFont.truetype(fp, int(W * 0.10))
        f_sub = ImageFont.truetype(fp, int(W * 0.052))

        zod = character.get("zodiac") or ""
        # 단계 라벨(상단)
        d.text((W // 2, int(H * 0.10)), str(scene.get("stage", "")), font=f_stage,
               fill=(255, 255, 255), anchor="mm")
        # 띠 배지(중앙) — v1 코드그래픽: 띠 글자를 캐릭터 상징으로
        if zod:
            d.text((W // 2, int(H * 0.40)), f"{zod}띠", font=f_zod, fill=(255, 255, 255), anchor="mm")
        # 자막(하단, 박스)
        txt = _wrap(scene.get("line", ""))
        bb = d.multiline_textbbox((0, 0), txt, font=f_sub, spacing=14, align="center")
        th = bb[3] - bb[1]
        y0 = int(H * 0.72)
        d.rectangle([W * 0.06, y0 - 30, W * 0.94, y0 + th + 30], fill=(0, 0, 0))
        d.multiline_text((W // 2, y0 + th // 2), txt, font=f_sub, fill=(255, 255, 255),
                         anchor="mm", spacing=14, align="center")
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_png)
        return out_png


class FluxStillRenderer(CodeGraphicRenderer):
    """사전 베이크된 FLUX '3D룩' 스틸 라이브러리 사용. 자산 없으면 code로 폴백."""

    name = "flux"

    def __init__(self, library_dir: str | None = None) -> None:
        self.lib = library_dir or os.path.join(os.path.dirname(__file__), "..", "assets", "video_stills")

    def render_scene(self, scene: dict, character: dict, W: int, H: int, out_png: str) -> str:
        zod = character.get("zodiac") or ""
        stage = scene.get("stage", "")
        # asset_key = {zodiac}_{stage} (성격 톤은 추후 컬러그레이드로 변조)
        cand = os.path.join(self.lib, f"{zod}_{stage}.png")
        if not os.path.exists(cand):
            # graceful 폴백: 코드그래픽(아직 미베이크 라이브러리)
            return super().render_scene(scene, character, W, H, out_png)
        # 스틸 + 자막 오버레이 (비율 보존 cover-crop — 늘어남/왜곡 방지)
        src = Image.open(cand).convert("RGB")
        sw, sh = src.size
        scale = max(W / sw, H / sh)
        src = src.resize((max(1, int(sw * scale)), max(1, int(sh * scale))))
        nw, nh = src.size
        left, top = (nw - W) // 2, (nh - H) // 2
        base = src.crop((left, top, left + W, top + H))
        d = ImageDraw.Draw(base)
        f_sub = ImageFont.truetype(_font_path(), int(W * 0.052))
        txt = _wrap(scene.get("line", ""))
        bb = d.multiline_textbbox((0, 0), txt, font=f_sub, spacing=14, align="center")
        th = bb[3] - bb[1]
        y0 = int(H * 0.72)
        d.rectangle([W * 0.06, y0 - 30, W * 0.94, y0 + th + 30], fill=(0, 0, 0))
        d.multiline_text((W // 2, y0 + th // 2), txt, font=f_sub, fill=(255, 255, 255),
                         anchor="mm", spacing=14, align="center")
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        base.save(out_png)
        return out_png


def get_renderer(kind: str) -> CodeGraphicRenderer:
    return FluxStillRenderer() if (kind or "code").lower() == "flux" else CodeGraphicRenderer()


# ───────────── 말하는 캐릭터(flap) 자산 ─────────────
_STILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "video_stills")
_TALK_STAGES = ["초년", "유년", "청년", "장년", "노년"]


def talking_available(zodiac: str) -> bool:
    """해당 띠의 5단계 모두 닫힘+입벌림 스틸이 베이크돼 있으면 True(말하는 캐릭터 가능)."""
    for st in _TALK_STAGES:
        base = os.path.join(_STILLS_DIR, f"{zodiac}_{st}.png")
        opn = os.path.join(_STILLS_DIR, f"{zodiac}_{st}_open.png")
        if not (os.path.exists(base) and os.path.exists(opn)):
            return False
    return True


def _cover_crop(src_path: str, W: int, H: int, out_png: str) -> str:
    """비율 보존 cover-crop(왜곡 없음) → W×H PNG."""
    src = Image.open(src_path).convert("RGB")
    sw, sh = src.size
    scale = max(W / sw, H / sh)
    src = src.resize((max(1, int(sw * scale)), max(1, int(sh * scale))))
    nw, nh = src.size
    left, top = (nw - W) // 2, (nh - H) // 2
    src.crop((left, top, left + W, top + H)).save(out_png)
    return out_png


def talking_stills(zodiac: str, stage: str, W: int, H: int, workdir: str, idx: int) -> tuple[str, str] | None:
    """zodiac+stage 닫힘/열림 스틸을 W×H cover-crop. (closed,open) 경로 or None(미베이크)."""
    base = os.path.join(_STILLS_DIR, f"{zodiac}_{stage}.png")
    opn = os.path.join(_STILLS_DIR, f"{zodiac}_{stage}_open.png")
    if not (os.path.exists(base) and os.path.exists(opn)):
        return None
    Path(workdir).mkdir(parents=True, exist_ok=True)
    c = os.path.join(workdir, f"closed_{idx}.png")
    o = os.path.join(workdir, f"open_{idx}.png")
    _cover_crop(base, W, H, c)
    _cover_crop(opn, W, H, o)
    return c, o


_VIS_KEYS = ["A", "O", "E"]


def viseme_shapes(zodiac: str, stage: str, W: int, H: int, workdir: str, idx: int) -> dict | None:
    """비세메 입모양 {closed,A,O,E}를 W×H cover-crop. 4종 다 베이크돼 있으면 dict, 아니면 None(→2단계 flap 폴백)."""
    base = os.path.join(_STILLS_DIR, f"{zodiac}_{stage}.png")
    srcs = {k: os.path.join(_STILLS_DIR, f"{zodiac}_{stage}_{k}.png") for k in _VIS_KEYS}
    if not (os.path.exists(base) and all(os.path.exists(v) for v in srcs.values())):
        return None
    Path(workdir).mkdir(parents=True, exist_ok=True)
    out = {"closed": _cover_crop(base, W, H, os.path.join(workdir, f"vcl_{idx}.png"))}
    for k, v in srcs.items():
        out[k] = _cover_crop(v, W, H, os.path.join(workdir, f"v{k}_{idx}.png"))
    return out


def render_subtitle_overlay(line: str, W: int, H: int, out_png: str) -> str:
    """투명 자막 오버레이(옅은 박스+외곽선). 워터마크/타이틀은 최종 오버레이가 담당."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fs = ImageFont.truetype(_font_path(), int(W * 0.052))
    txt = _wrap(line, 16)
    bb = d.multiline_textbbox((0, 0), txt, font=fs, spacing=14, align="center")
    th = bb[3] - bb[1]
    cy = int(H * 0.82)
    d.rounded_rectangle([W * 0.05, cy - th // 2 - int(H * 0.018), W * 0.95, cy + th // 2 + int(H * 0.018)],
                        radius=int(W * 0.024), fill=(0, 0, 0, 72))
    for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
        d.multiline_text((W // 2 + dx, cy + dy), txt, font=fs, fill=(0, 0, 0, 220),
                         anchor="mm", spacing=14, align="center")
    d.multiline_text((W // 2, cy), txt, font=fs, fill=(255, 255, 255, 255),
                     anchor="mm", spacing=14, align="center")
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def split_caption(line: str, maxc: int = 15) -> list[str]:
    """긴 문장을 음성 속도에 맞춰 띄울 짧은 구절들로 분할(구두점·길이 기준)."""
    import re as _re
    out: list[str] = []
    for part in _re.split(r"(?<=[.!?,…])\s+", (line or "").strip()):
        p = part.strip().rstrip(",")
        while len(p) > maxc:
            cut = p.rfind(" ", 0, maxc + 4)
            if cut <= 0:
                cut = maxc
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out or [line.strip()]


def render_caption(text: str, W: int, H: int, out_png: str) -> str:
    """짧은 구절 캡션(보조 역할). 박스 없음·반투명·작게·최하단 — 음성이 메인, 이미지 안 가림."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fs = ImageFont.truetype(_font_path(), int(W * 0.044))   # 작게(보조)
    txt = _wrap(text, 18, max_lines=2)
    cy = int(H * 0.93)                                       # 제일 아래(크레딧 바로 위)
    # 박스 없음 → 캐릭터 안 가림. 얇은 외곽선(가독성)만 + 반투명 텍스트.
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if dx * dx + dy * dy >= 5:
                continue
            d.multiline_text((W // 2 + dx, cy + dy), txt, font=fs, fill=(0, 0, 0, 140),
                             anchor="mm", spacing=8, align="center")
    d.multiline_text((W // 2, cy), txt, font=fs, fill=(255, 255, 255, 200),
                     anchor="mm", spacing=8, align="center")
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png
