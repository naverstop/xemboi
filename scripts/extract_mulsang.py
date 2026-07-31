# -*- coding: utf-8 -*-
"""명리전 물상 조합 사전 추출 — 결정적 파서(LLM 불요).

1권(vision 복원본): 지지 조합 144항목 'N. 寅木이 卯木을 만나면' + 물상 해설
2권(정상 추출본):   천간 조합 100항목 'N. 甲木에 乙木이 있으면' + 물상 해설

원문 그대로 추출해 data/rag/mulsang_pairs.json 으로 저장한다(관법 B2 — 선생님 책 원문이라
해설 창작 없음). 이후 명식에 실존하는 조합의 원문 해설을 결정적으로 주입하는 데 쓴다.

실행: .venv/Scripts/python.exe -m scripts.extract_mulsang
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

BOOK1 = PROJECT_ROOT / "data" / "ocr" / "명리전 1 최종.txt"
BOOK2 = PROJECT_ROOT / "data" / "processed" / "명리전 제2권 완성(책).txt"
OUT = PROJECT_ROOT / "data" / "rag" / "mulsang_pairs.json"

_STEMS = "甲乙丙丁戊己庚辛壬癸"
_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
_ELEM = "木火土金水"

# 1권: 'N. 寅木이 卯木을 만나면' (한 줄 헤딩, vision 전사라 줄 안정적)
_B1_HEAD = re.compile(
    rf"^\s*(\d+)\.\s*([{_BRANCHES}])[{_ELEM}]?[이가]\s*([{_BRANCHES}])[{_ELEM}]?[을를]\s*만나면\s*$",
    re.M,
)
# 2권: 'N. 甲木에 乙木이 있으면' (줄바꿈·붙여쓰기 혼재라 토큰 사이 공백 허용)
_B2_HEAD = re.compile(
    rf"(\d+)\.\s*([{_STEMS}])[{_ELEM}]?\s*에\s*([{_STEMS}{_BRANCHES}])[{_ELEM}]?\s*[가이]?\s*있으면"
)
_PAGE_B1 = re.compile(r"^===== p\.(\d+) =====$", re.M)
_PAGE_B2 = re.compile(r"-\s*(\d+)\s*-")


def _page_at(markers: list[tuple[int, int]], pos: int) -> int | None:
    """pos 직전 페이지 마커의 페이지 번호."""
    page = None
    for mpos, p in markers:
        if mpos > pos:
            break
        page = p
    return page


def _clean(body: str) -> str:
    """항목 본문 정리 — 페이지 마커·쪽번호·꼬리말·장식 헤더 제거, 과도한 공백 축소."""
    body = _PAGE_B1.sub("", body)
    body = re.sub(r"^\s*-\s*\d+\s*-\s*$", "", body, flags=re.M)
    body = re.sub(r"^\s*[⧓▶◀]+.*[⧓▶◀]+\s*$", "", body, flags=re.M)
    body = re.sub(r"©.*금지", "", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _fix_book1_ocr(text: str) -> str:
    """지지 조합 헤딩('…만나면')의 戌→戊 비전 오인식 교정(자형 유사, 실측 8건).

    이 챕터의 주어·목적어는 지지뿐이라 '만나면' 문형 안의 戊土는 전부 戌土가 정답 —
    스코프를 헤딩 줄로 한정해 본문 속 진짜 戊土(천간 서술)는 건드리지 않는다."""
    def _fix_line(m: "re.Match[str]") -> str:
        return m.group(0).replace("戊土", "戌土")
    return re.sub(rf"^\s*\d+\.\s*\S+[이가]\s*\S+[을를]\s*만나면\s*$", _fix_line, text, flags=re.M)


def _extract(text: str, head_re: re.Pattern, page_re: re.Pattern, kind: str,
             src_label: str, min_len: int = 150) -> list[dict]:
    markers = [(m.start(), int(m.group(1))) for m in page_re.finditer(text)]
    heads = list(head_re.finditer(text))
    out: list[dict] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else min(len(text), m.end() + 4000)
        body = _clean(text[m.end(): end])
        if len(body) < min_len:   # 목차 줄(본문 없음)은 제외
            continue
        a, b = m.group(2), m.group(3)
        out.append({
            "kind": kind, "a": a, "b": b,
            "title": re.sub(r"\s+", " ", m.group(0)).strip(),
            "text": body,
            "source": f"{src_label} p.{_page_at(markers, m.start()) or '?'}",
        })
    return out


def main() -> int:
    entries: list[dict] = []
    if BOOK1.exists():
        t1 = _fix_book1_ocr(BOOK1.read_text(encoding="utf-8", errors="replace"))
        e1 = _extract(t1, _B1_HEAD, _PAGE_B1, "branch", "명리전1권")
        print(f"[1권] 지지 조합 {len(e1)}항목")
        entries += e1
    if BOOK2.exists():
        t2 = BOOK2.read_text(encoding="utf-8", errors="replace")
        e2 = _extract(t2, _B2_HEAD, _PAGE_B2, "stem", "명리전2권")
        print(f"[2권] 천간 조합 {len(e2)}항목")
        entries += e2
    # (a,b) 중복 시 본문 긴 쪽 유지(목차 잔재·중복 스캔 대비)
    best: dict[tuple, dict] = {}
    for e in entries:
        k = (e["kind"], e["a"], e["b"])
        if k not in best or len(e["text"]) > len(best[k]["text"]):
            best[k] = e
    final = sorted(best.values(), key=lambda e: (e["kind"], e["a"], e["b"]))
    OUT.write_text(json.dumps({"_README": "명리전 물상 조합 사전(원문 발췌, 결정적 파서 산출). "
                               "kind=branch(1권 지지쌍)/stem(2권 천간쌍). 명식 실존 쌍 주입용.",
                               "entries": final}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[저장] {OUT.name}: {len(final)}항목 (지지 {sum(1 for e in final if e['kind']=='branch')}, "
          f"천간 {sum(1 for e in final if e['kind']=='stem')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
