"""ffmpeg 합성 + 4K 인코딩(부록 A-4/B-7, PoC e2e 검증).

장면별 (프레임 PNG + TTS wav) → zoompan 클립 → concat → 4K lanczos 업스케일
→ hevc_nvenc 10bit(또는 libx264 CPU) 마스터. -14 LUFS loudnorm.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from backend.app.services.video import renderer as _rnd

_RES = {  # aspect → (생성 W,H, 4K W,H)
    "9x16": (1080, 1920, 2160, 3840),
    "16x9": (1920, 1080, 3840, 2160),
}


def _ffprobe_dur(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 3.0


def _gpu_free_mb(idx: int) -> int:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", f"--id={idx}"],
            capture_output=True, text=True,
        )
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return 0


def _pick_encoder(mode: str, vram_gate_mb: int, gpu_index: int = 1) -> tuple[list[str], str, bool]:
    """(ffmpeg 비디오 인코딩 인자, encoder_used, gpu_gate_fallback). 사주 자원 정책: GPU1+CPU만 사용."""
    mode = (mode or "cpu").lower()
    nvenc = ["-c:v", "hevc_nvenc", "-preset", "p5", "-rc", "vbr", "-pix_fmt", "p010le",
             "-maxrate", "25M", "-bufsize", "50M", "-gpu", str(gpu_index)]
    libx = ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if mode == "nvenc":
        return nvenc, "hevc_nvenc", False
    if mode == "auto":
        if _gpu_free_mb(gpu_index) >= vram_gate_mb:
            return nvenc, "hevc_nvenc", False
        return libx, "libx264", True  # GPU1 혼잡(LLM 등) → CPU 폴백
    return libx, "libx264", False     # cpu(기본)


def compose(
    scenes: list[dict],           # 각: {frame: png, wav: wav, ...}
    aspect: str,
    out_path: str,
    workdir: str,
    encoder_mode: str = "cpu",
    cq: int = 20,
    vram_gate_mb: int = 3000,
    overlay_png: str | None = None,   # 고정 워터마크/타이틀 오버레이(스케일 후 합성)
    gpu_index: int = 1,
) -> tuple[str, str, bool]:
    """장면들 → 4K mp4. 반환 (out_path, encoder_used, gpu_gate_fallback)."""
    W, H, UW, UH = _RES.get(aspect, _RES["9x16"])
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)

    clips: list[str] = []
    for i, sc in enumerate(scenes):
        dur = _ffprobe_dur(sc["wav"])
        n = max(1, int(dur * 30))
        clip = str(wd / f"clip_{i}.mp4")
        vf = (f"scale={W}:{H},zoompan=z='min(zoom+0.0009,1.13)':d={n}:s={W}x{H}:fps=30,"
              f"format=yuv420p")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", sc["frame"],
             "-i", sc["wav"], "-vf", vf, "-t", f"{dur:.2f}", "-r", "30",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "192k", "-shortest", clip],
            check=True, capture_output=True,
        )
        clips.append(clip)

    listf = wd / "concat.txt"
    listf.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    use_overlay = bool(overlay_png and Path(overlay_png).exists())

    def _cmd(video_enc: list[str]) -> list[str]:
        inputs = ["-f", "concat", "-safe", "0", "-i", str(listf)]
        if use_overlay:
            inputs += ["-i", overlay_png]
            fc = (f"[0:v]scale={UW}:{UH}:flags=lanczos[bg];[bg][1:v]overlay=0:0[v];"
                  f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        else:
            fc = (f"[0:v]scale={UW}:{UH}:flags=lanczos[v];"
                  f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        return [
            "ffmpeg", "-y", "-loglevel", "error", *inputs,
            "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            *video_enc, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", out_path,
        ]

    enc, used, fb = _pick_encoder(encoder_mode, vram_gate_mb, gpu_index)
    enc = enc + (["-cq", str(cq)] if used == "hevc_nvenc" else ["-crf", str(min(cq, 23))])
    r = subprocess.run(_cmd(enc), capture_output=True, text=True)
    if r.returncode != 0:
        # nvenc 실패 → libx264 폴백
        libx = ["-c:v", "libx264", "-preset", "medium", "-crf", str(min(cq, 23)), "-pix_fmt", "yuv420p"]
        subprocess.run(_cmd(libx), check=True, capture_output=True)
        used, fb = "libx264", True
    return out_path, used, fb


# ───────────────────────── 말하는 캐릭터(진폭 동기화 flap) ─────────────────────────
def _envelope(wav: str, fps: int = 30) -> np.ndarray:
    """오디오 RMS 진폭 포락선(프레임당)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", wav, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = 16000 // fps
    if len(a) < hop:
        return np.zeros(1)
    n = len(a) // hop
    return np.array([np.sqrt(np.mean(a[k * hop:(k + 1) * hop] ** 2) + 1e-9) for k in range(n)])


def _dwell(st: np.ndarray, minrun: int = 3) -> np.ndarray:
    """최소 유지(떨림 방지)."""
    st = list(st)
    out = [st[0]]
    cur = st[0]
    run = 1
    for v in st[1:]:
        if v == cur or run < minrun:
            out.append(cur)
            run += 1
        else:
            cur = v
            out.append(cur)
            run = 1
    return np.array(out)


def _mouth_states(wav: str, pad: float = 0.6, fps: int = 30) -> np.ndarray:
    """진폭>임계 → 입 열림(1)/닫힘(0). 무음 패딩=닫힘. 말할 때 열리고 쉴 때 닫힘."""
    rms = _envelope(wav, fps)
    if rms.max() < 1e-6:
        st = np.zeros(len(rms), dtype=int)
    else:
        thr = max(0.02, rms.max() * 0.16)
        st = _dwell((rms > thr).astype(int), 3)
    return np.concatenate([st, np.zeros(int(pad * fps), dtype=int)])


_WHISPER = None


def _whisper():
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel
        _WHISPER = WhisperModel("small", device="cpu", compute_type="int8")
    return _WHISPER


_VOW_A = {0, 1, 2, 3, 9, 10}      # ㅏㅐㅑㅒㅘㅙ → 크게 벌림
_VOW_O = {8, 11, 12, 13, 14, 15, 17}  # ㅗㅚㅛㅜㅝㅞㅠ → 오므림


def _vowel_viseme(ch: str) -> str | None:
    if not ("가" <= ch <= "힣"):
        return None
    j = (ord(ch) - 0xAC00) // 28 % 21
    return "A" if j in _VOW_A else "O" if j in _VOW_O else "E"


def _viseme_frames(wav: str, pad: float, fps: int = 30) -> list[str]:
    """Whisper 단어 타이밍 → 음절별 모음 비세메(A/O/E). 단어 사이·무음=closed. 정밀 립싱크."""
    dur = _ffprobe_dur(wav)
    nF = max(1, int((dur + pad) * fps))
    seq = ["closed"] * nF
    try:
        segs, _ = _whisper().transcribe(wav, language="ko", word_timestamps=True)
        words = [(w.start, w.end, w.word) for s in segs for w in (s.words or [])]
    except Exception:
        words = []
    for st, en, wd in words:
        syl = [c for c in wd if "가" <= c <= "힣"]
        if not syl or en <= st:
            continue
        seg = (en - st) / len(syl)
        for k, c in enumerate(syl):
            v = _vowel_viseme(c) or "E"
            f0, f1 = int((st + k * seg) * fps), int((st + (k + 1) * seg) * fps)
            for f in range(max(0, f0), min(nF, f1)):
                seq[f] = v
    # 디바운스(최소 2프레임 유지 — 깜빡임 방지)
    out = [seq[0]]
    cur, run = seq[0], 1
    for v in seq[1:]:
        if v == cur or run < 2:
            out.append(cur); run += 1
        else:
            cur, run = v, 1; out.append(cur)
    return out


def compose_talking(
    scenes: list[dict],           # 각: {closed, open, wav, sub}(png/wav 경로)
    aspect: str,
    out_path: str,
    workdir: str,
    encoder_mode: str = "cpu",
    cq: int = 20,
    vram_gate_mb: int = 3000,
    overlay_png: str | None = None,
    pad: float = 0.6,
    xfade: float = 0.45,
    bgm_path: str | None = None,
    bgm_volume: float = 0.16,
    credit: str | None = None,
    gpu_index: int = 1,
) -> tuple[str, str, bool]:
    """입 열림/닫힘 스틸을 음성 진폭에 맞춰 flap(말하는 효과) → fadewhite 전환 → 4K.

    몸은 고정·입만 변해 뭉개짐 0. xfade(<pad)는 무음 구간에서 일어나 목소리 미중복.
    반환 (out_path, encoder_used, gpu_gate_fallback).
    """
    W, H, UW, UH = _RES.get(aspect, _RES["9x16"])
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)

    scene_clips: list[str] = []
    for i, sc in enumerate(scenes):
        wav = sc["wav"]
        closed = sc["closed"]
        opn = sc.get("open") or closed
        sub = sc["sub"]
        dur = _ffprobe_dur(wav)
        sdur = dur + pad
        # ─────────────────────────────────────────────────────────────────────────────
        # ⚠️ 입 움직임(립싱크/진폭 flap) 비활성화(2026-06-29): 현 2D 입모양이 부자연스러워
        #    정지 입(닫힘 스틸)으로 생성. 나중에 다른 립싱크 엔진(예: 리깅3D/Audio2Face/MuseTalk)
        #    도입 시 아래 블록 주석 해제하면 비세메+진폭 flap 복원됨.
        #    (관련 엔진 함수 _viseme_frames/_mouth_states/_envelope/_dwell/_vowel_viseme/_whisper
        #     및 renderer.viseme_shapes·talking_stills의 open 스틸은 보존됨.)
        # viseme = sc.get("viseme")   # {closed,A,O,E} or None
        # if viseme:                  # 비세메 립싱크(Whisper 음절 타이밍 → 모음별 입모양)
        #     seq = _viseme_frames(wav, pad, fps=30)
        #     shape = lambda lab: viseme.get(lab, viseme["closed"])
        # else:                       # 폴백: 진폭 2단계 flap
        #     seq = ["open" if x == 1 else "closed" for x in _mouth_states(wav, pad=pad, fps=30)]
        #     shape = lambda lab: (opn if lab == "open" else closed)
        # # 입모양 시퀀스 → RLE → concat 리스트
        # lst = wd / f"flap_{i}.txt"
        # lines: list[str] = []
        # j, n = 0, len(seq)
        # while j < n:
        #     k = j
        #     while k < n and seq[k] == seq[j]:
        #         k += 1
        #     lines.append(f"file '{shape(seq[j]).replace(chr(92), '/')}'")
        #     lines.append(f"duration {(k - j) / 30.0:.4f}")
        #     j = k
        # lines.append(f"file '{shape(seq[-1]).replace(chr(92), '/')}'")  # concat 규칙: 마지막 프레임
        # lst.write_text("\n".join(lines), encoding="utf-8")
        # 정지 입: 닫힘 스틸 한 장을 장면 길이만큼 고정(입 움직임 없음)
        lst = wd / f"flap_{i}.txt"
        _cl = closed.replace(chr(92), "/")
        lst.write_text(f"file '{_cl}'\nduration {sdur:.4f}\nfile '{_cl}'\n", encoding="utf-8")
        # 자막: 긴 문장을 짧은 구절로 쪼개 음성 속도에 맞춰 순차 표시(쇼츠형 캡션)
        phrases = _rnd.split_caption(sc.get("line", ""))
        total_ch = sum(len(p) for p in phrases) or 1
        cap_files: list[str] = []
        chain: list[tuple[int, float, float]] = []
        t_acc = 0.0
        for k, ph in enumerate(phrases):
            cp = str(wd / f"cap_{i}_{k}.png")
            _rnd.render_caption(ph, W, H, cp)
            cap_files.append(cp)
            seg = dur * len(ph) / total_ch
            start, end = t_acc, (sdur if k == len(phrases) - 1 else t_acc + seg)
            chain.append((2 + k, start, end))   # 입력 인덱스: concat[0], wav[1], 캡션[2..]
            t_acc += seg
        sc_out = str(wd / f"scene_{i}.mp4")
        inp_args = ["-f", "concat", "-safe", "0", "-i", str(lst), "-i", wav]
        for cp in cap_files:
            inp_args += ["-i", cp]
        fc = f"[0:v]fps=30,scale={W}:{H},setsar=1[base]"
        prev = "[base]"
        for jx, (idx, s, e) in enumerate(chain):
            lbl = f"[c{jx}]"
            fc += f";{prev}[{idx}:v]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})'{lbl}"
            prev = lbl
        fc += f";[1:a]apad=pad_dur={pad}[a]"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *inp_args,
             "-filter_complex", fc, "-map", prev, "-map", "[a]", "-t", f"{sdur:.2f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", sc_out],
            check=True, capture_output=True,
        )
        scene_clips.append(sc_out)

    durs = [_ffprobe_dur(c) for c in scene_clips]
    inp: list[str] = []
    for c in scene_clips:
        inp += ["-i", c]
    use_overlay = bool(overlay_png and Path(overlay_png).exists())
    parts: list[str] = []
    pv, pa, acc = "[0:v]", "[0:a]", durs[0]
    for i in range(1, len(scene_clips)):
        off = max(0.1, acc - xfade)
        nv, na = f"[v{i}]", f"[a{i}]"
        parts.append(f"{pv}[{i}:v]xfade=transition=fadewhite:duration={xfade}:offset={off:.3f}{nv}")
        parts.append(f"{pa}[{i}:a]acrossfade=d={xfade}{na}")
        pv, pa, acc = nv, na, acc + durs[i] - xfade
    if use_overlay:
        ov_idx = len(scene_clips)
        inp += ["-i", overlay_png]
        parts.append(f"{pv}scale={UW}:{UH}:flags=lanczos[bg];[bg][{ov_idx}:v]overlay=0:0[vout]")
    else:
        parts.append(f"{pv}scale={UW}:{UH}:flags=lanczos[vout]")
    # 오디오: 내레이션 + BGM(루프·저볼륨·페이드) 믹싱 후 최종 loudnorm
    use_bgm = bool(bgm_path and Path(bgm_path).exists())
    if use_bgm:
        bgm_idx = len(scene_clips) + (1 if use_overlay else 0)
        inp += ["-stream_loop", "-1", "-i", bgm_path]   # 영상 길이만큼 루프
        _fo = max(2.0, acc - 2.5)
        parts.append(f"[{bgm_idx}:a]volume={bgm_volume},afade=t=in:st=0:d=2,afade=t=out:st={_fo:.1f}:d=2.5[bgm]")
        parts.append(f"{pa}[bgm]amix=inputs=2:duration=first:normalize=0[amx]")
        parts.append(f"[amx]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    else:
        parts.append(f"{pa}loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    fc = ";".join(parts)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    _meta: list[str] = []
    if credit:
        _meta = ["-metadata", f"artist={credit}", "-metadata", f"author={credit}",
                 "-metadata", f"copyright={credit}", "-metadata", f"comment=음원·영상 출처 {credit}"]

    def _cmd(video_enc: list[str]) -> list[str]:
        return [
            "ffmpeg", "-y", "-loglevel", "error", *inp,
            "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
            *video_enc, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            *_meta,
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", out_path,
        ]

    enc, used, fb = _pick_encoder(encoder_mode, vram_gate_mb, gpu_index)
    enc = enc + (["-cq", str(cq)] if used == "hevc_nvenc" else ["-crf", str(min(cq, 23))])
    r = subprocess.run(_cmd(enc), capture_output=True, text=True)
    if r.returncode != 0:
        libx = ["-c:v", "libx264", "-preset", "medium", "-crf", str(min(cq, 23)), "-pix_fmt", "yuv420p"]
        subprocess.run(_cmd(libx), check=True, capture_output=True)
        used, fb = "libx264", True
    return out_path, used, fb
