"""Pluggable TTS — 성별·캐릭터(생애단계·무드)별 최적 음성 더빙(부록 C-8 + 보완).

성별 정확도: edge-tts만 한국어 남/여 모두 지원(InJoon/Hyunsu 남, SunHi 여).
Windows SAPI(Heami)는 한국어 '여성 1종'뿐 → 남성 사주는 불가(폴백 한계, 문서화).
캐릭터 매핑: 생애단계→피치(유년↑·노년↓), 무드→속도(밝음↑·회상↓), 남성 단계→음색(청년 Hyunsu/중장년 InJoon).
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

# OpenAI gpt-4o-mini-tts — 자연스럽고 감정 있는 한국어(지시 instructions로 감정·나이 제어)
# 생애단계별 나이 목소리(초년→유년→청년→장년→노년)
_OAI_AGE = {
    "초년": "맑고 귀엽고 아주 높은 갓난아기(2~3세) 목소리로, 천진하게",
    "유년": "맑고 높은 어린이(6~8세) 목소리로, 밝고 천진난만하게",
    "청년": "활기차고 또렷한 20대 청년 목소리로",
    "장년": "차분하고 묵직한 40~50대 중년 목소리로",
    "노년": "따뜻하고 여유로운 70대 노년 목소리로, 조금 느리고 부드럽게",
}


def _oai_voice(gender: str, stage: str) -> str:
    fem = (gender or "male").lower() == "female"
    if stage in ("초년", "유년"):
        return "coral"                      # 아기·어린이 — 밝고 높은 톤(성별 무관)
    if stage == "청년":
        return "nova" if fem else "echo"     # 젊은 목소리
    return "shimmer" if fem else "onyx"      # 장년·노년(중후)
_OAI_EMO = {
    "설렘": "설레고 기대에 찬 밝은 톤", "기쁨": "기쁘고 활기찬 톤", "희망": "희망차고 따뜻한 톤",
    "벅참": "벅차고 감격스러운 톤", "평온": "잔잔하고 평온한 톤", "회상": "그리움이 묻어나는 잔잔한 톤",
    "아쉬움": "아쉽고 애틋한 톤", "결연": "단단하고 결연한 톤", "위트": "장난스럽고 유쾌한 톤",
    "밝음": "밝고 경쾌한 톤", "차분": "차분하고 안정된 톤",
}


_BABY_PITCH = {"초년": 5.0, "유년": 3.0}   # 아기·어린이 — 성인 TTS 피치업해 음색 근사(승인본)


def _audio_sr(wav: str) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=sample_rate", "-of", "csv=p=0", wav],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except (ValueError, AttributeError):
        return 24000


def _pitch_up(wav: str, semitones: float) -> None:
    """피치(+성대 크기 효과)만 올리고 길이 유지 — 애기 목소리 근사. 실패 시 원본 유지."""
    f = 2 ** (semitones / 12.0)
    sr = _audio_sr(wav)
    tmp = wav + ".pitch.wav"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                        "-af", f"asetrate={sr}*{f:.4f},aresample={sr},atempo={1/f:.4f}", tmp],
                       capture_output=True)
    if r.returncode == 0 and Path(tmp).exists() and Path(tmp).stat().st_size > 1000:
        os.replace(tmp, wav)


def _openai_key() -> str | None:
    k = os.getenv("OPENAI_API_KEY")
    if k:
        return k.strip().strip('"').strip("'")
    env = Path(__file__).resolve().parents[4] / ".env"
    try:
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def _openai(text: str, out_wav: str, gender: str, emotion: str, stage: str = "") -> None:
    key = _openai_key()
    if not key:
        raise TtsError("no openai key")
    voice = _oai_voice(gender, stage)
    age = _OAI_AGE.get(stage, "")
    instr = (f"{age} 한국어 내레이션. 자신의 인생 이야기를 들려주듯 자연스럽고 또박또박, "
             f"기계음 없이 진짜 사람처럼. " + _OAI_EMO.get(emotion, "감정이 자연스럽게 묻어나게"))
    body = json.dumps({"model": "gpt-4o-mini-tts", "voice": voice, "input": text,
                       "instructions": instr, "response_format": "wav"}).encode("utf-8")
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    Path(out_wav).write_bytes(data)
    if Path(out_wav).stat().st_size < 1000:
        raise TtsError("openai tts empty")

# ── 음성/프로소디 매핑 ────────────────────────────────────────────
_EDGE_FEMALE = "ko-KR-SunHiNeural"
_EDGE_MALE_YOUNG = "ko-KR-HyunsuMultilingualNeural"   # 초년/유년/청년
_EDGE_MALE_MATURE = "ko-KR-InJoonNeural"              # 장년/노년
_YOUNG_STAGES = {"초년", "유년", "청년"}
_PITCH_BY_STAGE = {"초년": 10, "유년": 8, "청년": 4, "장년": 0, "노년": -6}

# ── 감정선 이입: 감정 → (속도%, 피치Hz, 볼륨%) ──────────────────
# 빠르고 높고 크면 고조(기쁨·벅참), 느리고 낮고 작으면 이완(회상·아쉬움).
# 생애단계 피치(_PITCH_BY_STAGE)와 합산되어 캐릭터+감정이 함께 실린다.
_EMOTION_PROSODY = {
    "설렘":  (6,  3,  2),
    "기쁨":  (12, 6,  8),
    "희망":  (5,  3,  4),
    "벅참":  (-4, 5,  12),   # 느리지만 힘있게·크게(클라이맥스)
    "평온":  (-3, 0,  0),
    "회상":  (-12, -4, -8),  # 느리고 낮고 작게(잔잔한 추억)
    "아쉬움": (-14, -6, -10),
    "결연":  (3,  -2, 7),
    "위트":  (13, 7,  3),
    # mood 폴백
    "밝음":  (10, 5,  6),
    "차분":  (-4, 0,  0),
}
_DEFAULT_PROSODY = (0, 0, 0)
# Heami($s.Rate 정수 -10..10) — 감정별 속도(성별은 여성 고정)
_HEAMI_RATE_BY_EMO = {
    "기쁨": 2, "위트": 3, "설렘": 2, "희망": 1, "벅참": -1,
    "평온": -1, "차분": -1, "회상": -2, "아쉬움": -2, "결연": 1,
}


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class TtsError(Exception):
    pass


def select_voice(gender: str, stage: str) -> str:
    """성별·생애단계 → edge-tts 음성명."""
    if (gender or "male").lower() == "female":
        return _EDGE_FEMALE
    return _EDGE_MALE_YOUNG if stage in _YOUNG_STAGES else _EDGE_MALE_MATURE


def _edgetts(text: str, out_wav: str, gender: str, stage: str, emotion: str) -> None:
    try:
        import asyncio
        import edge_tts  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise TtsError(f"edge_tts not installed: {e}")
    voice = select_voice(gender, stage)
    er, ep, ev = _EMOTION_PROSODY.get(emotion, _DEFAULT_PROSODY)
    rate = _clamp(er, -25, 25)
    pitch = _clamp(_PITCH_BY_STAGE.get(stage, 0) + ep, -20, 20)   # 단계+감정 합산
    volume = _clamp(ev, -20, 20)
    rate_s, pitch_s, vol_s = f"{rate:+d}%", f"{pitch:+d}Hz", f"{volume:+d}%"

    async def _go() -> None:
        await edge_tts.Communicate(
            text, voice, rate=rate_s, pitch=pitch_s, volume=vol_s
        ).save(out_wav)

    asyncio.run(_go())
    if not Path(out_wav).exists():
        raise TtsError("edgetts produced no file")


def _heami(text: str, out_wav: str, emotion: str = "") -> None:
    """Windows SAPI(Heami, ko-KR 여성). 남성 불가 → 여성으로만 동작(폴백 한계)."""
    safe = text.replace("'", "''")
    rate = _HEAMI_RATE_BY_EMO.get(emotion, 0)
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try{$s.SelectVoice('Microsoft Heami Desktop')}catch{}; "
        f"$s.Rate={rate}; "
        f"$s.SetOutputToWaveFile('{out_wav}'); $s.Speak('{safe}'); $s.Dispose()"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not Path(out_wav).exists():
        raise TtsError(f"heami synth failed: {r.stderr[:200]}")


def synth(
    engine: str, text: str, out_wav: str,
    gender: str = "male", stage: str = "", emotion: str = "",
) -> str:
    """텍스트 → 성별·캐릭터·감정선 맞춤 음성. 엔진 미가용 시 안전 폴백.

    - edgetts: 성별·생애단계·감정(속도·피치·볼륨) 완전 반영(남/여 모두). 권장 기본.
    - heami  : 여성 전용. 남성 요청 시에도 여성으로 합성됨(한계) → 남성은 edgetts 우선.
    """
    text = (text or "").strip()
    if not text:
        raise TtsError("empty text")
    Path(out_wav).parent.mkdir(parents=True, exist_ok=True)
    eng = (engine or "openai").lower()
    male = (gender or "male").lower() != "female"

    if eng == "openai":
        # OpenAI gpt-4o-mini-tts(자연·감정·나이) → 실패 시 edgetts → heami 폴백
        try:
            _openai(text, out_wav, gender, emotion, stage)
            if stage in _BABY_PITCH:       # 아기·어린이 = 피치업(승인본)
                _pitch_up(out_wav, _BABY_PITCH[stage])
            return out_wav
        except Exception:  # noqa: BLE001
            try:
                _edgetts(text, out_wav, gender, stage, emotion)
                return out_wav
            except TtsError:
                _heami(text, out_wav, emotion)
                return out_wav

    if eng == "heami" and male:
        # Heami는 남성 불가 → 성별 정확도 위해 edgetts로 자동 승격(가능 시)
        try:
            _edgetts(text, out_wav, gender, stage, emotion)
            return out_wav
        except TtsError:
            _heami(text, out_wav, emotion)   # edgetts 불가 환경 → 여성으로라도(한계)
            return out_wav

    if eng == "edgetts":
        try:
            _edgetts(text, out_wav, gender, stage, emotion)
            return out_wav
        except TtsError:
            _heami(text, out_wav, emotion)   # 폴백(여성)
            return out_wav

    # heami(여성) 또는 미구현 엔진(melo 등) → heami
    _heami(text, out_wav, emotion)
    return out_wav
