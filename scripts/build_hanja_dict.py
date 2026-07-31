"""인명용 한자 사전 구축 — Unicode Unihan DB에서 작명용 데이터 추출.

추출 항목(글자당):
  ko      : 한글 음 (kHangul, 대표 1음 + 보조음 목록)
  strokes : 총획수 (kTotalStrokes)
  radical : 강희자전 부수 번호 1~214 (kRSUnicode/kRSKangXi) — 자원오행은 엔진에서 부수→오행 매핑
  defn    : 영문 뜻 (kDefinition, 참고용)

출력: data/naming/hanja_dict.json  { "強": {"ko":["강"],"strokes":11,"radical":57,"defn":"..."}, ... }

한글 음(kHangul)이 있는 CJK 한자만 수록(한국에서 읽히는 한자 = 인명용 후보 상위집합).
대법원 인명용한자 공식 목록과의 교집합 필터는 후속 정제 항목.

사용: python scripts/build_hanja_dict.py
"""
from __future__ import annotations

import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

UNIHAN_URL = "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip"
OUT = Path(__file__).resolve().parents[1] / "data" / "naming" / "hanja_dict.json"

# 필요한 Unihan 멤버 파일과 그 안의 필드
WANT_FIELDS = {
    "kHangul", "kTotalStrokes", "kRSUnicode", "kRSKangXi", "kDefinition",
}


def _download() -> bytes:
    print(f"[1/4] Unihan 다운로드: {UNIHAN_URL}")
    req = urllib.request.Request(UNIHAN_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    print(f"      {len(data)/1e6:.1f} MB 받음")
    return data


def _parse(zip_bytes: bytes) -> dict[str, dict]:
    print("[2/4] 파싱")
    fields: dict[str, dict[str, str]] = {}  # cp_hex -> {field: value}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            if not name.endswith(".txt"):
                continue
            with z.open(name) as f:
                for raw in io.TextIOWrapper(f, encoding="utf-8"):
                    if not raw or raw[0] == "#":
                        continue
                    parts = raw.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    cp, field, value = parts[0], parts[1], parts[2]
                    if field not in WANT_FIELDS:
                        continue
                    fields.setdefault(cp, {})[field] = value
    return fields


def _hangul_readings(khangul: str) -> list[str]:
    """kHangul 예: '강:0E 항:0N' → ['강','항'] (대표음 우선)."""
    out: list[str] = []
    for tok in khangul.split():
        syl = tok.split(":")[0].strip()
        if syl and syl not in out:
            out.append(syl)
    return out


def _radical(fields: dict[str, str]) -> int | None:
    """kRSUnicode '57.0' 또는 kRSKangXi '57.0' → 57."""
    for key in ("kRSUnicode", "kRSKangXi"):
        v = fields.get(key)
        if not v:
            continue
        m = re.match(r"(\d+)", v.split()[0])
        if m:
            return int(m.group(1))
    return None


def _strokes(v: str | None) -> int | None:
    if not v:
        return None
    m = re.match(r"(\d+)", v.split()[0])
    return int(m.group(1)) if m else None


def build() -> dict[str, dict]:
    raw = _parse(_download())
    print("[3/4] 사전 구성 (한글음 보유 한자만)")
    out: dict[str, dict] = {}
    for cp, f in raw.items():
        kh = f.get("kHangul")
        if not kh:  # 한국에서 읽히는 한자만
            continue
        try:
            ch = chr(int(cp[2:], 16))  # 'U+5F37' -> 強
        except Exception:  # noqa: BLE001
            continue
        ko = _hangul_readings(kh)
        strokes = _strokes(f.get("kTotalStrokes"))
        radical = _radical(f)
        if not ko or strokes is None or radical is None:
            continue
        entry: dict = {"ko": ko, "strokes": strokes, "radical": radical}
        defn = f.get("kDefinition")
        if defn:
            entry["defn"] = defn[:120]
        out[ch] = entry
    return out


def main() -> int:
    d = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fp:
        json.dump(d, fp, ensure_ascii=False)
    size_mb = OUT.stat().st_size / 1e6
    print(f"[4/4] 저장: {OUT}  ({len(d):,}자, {size_mb:.1f} MB)")
    # 표본 출력
    for ch in list(d)[:5]:
        print("   ", ch, d[ch])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
