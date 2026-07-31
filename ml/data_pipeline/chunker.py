"""텍스트 청킹: 학습자료 txt → RAG chunks.

전략:
- 문단(빈 줄) 단위로 1차 분할
- 각 문단을 토큰(=문자 근사) 기준 target_size로 합치되 max_size 초과 금지
- 너무 긴 문단은 문장(., 。, ?, !, ?, !) 기준으로 재분할
- chunk끼리 overlap_size 만큼 겹침 (검색 누락 방지)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SENT_SPLIT_RE = re.compile(r"(?<=[\.。\?!\?!])\s+")


@dataclass
class Chunk:
    source: str          # 파일 이름 (확장자 제외)
    chunk_id: int        # 같은 source 내 0부터 증가
    text: str
    char_len: int


def _split_paragraphs(text: str) -> list[str]:
    # 페이지 마커, 다중 공백 정규화
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paras


def _split_sentences(paragraph: str, max_size: int) -> list[str]:
    """긴 문단을 문장 기준으로 재분할. 그래도 길면 max_size로 강제 절단."""
    sents = SENT_SPLIT_RE.split(paragraph)
    out: list[str] = []
    for s in sents:
        s = s.strip()
        if not s:
            continue
        if len(s) <= max_size:
            out.append(s)
        else:
            # 강제 절단
            for i in range(0, len(s), max_size):
                out.append(s[i : i + max_size])
    return out


def chunk_text(
    text: str,
    *,
    target_size: int = 700,
    max_size: int = 1000,
    overlap_size: int = 120,
) -> list[str]:
    """텍스트를 chunk 문자열 리스트로 반환."""
    paragraphs = _split_paragraphs(text)
    units: list[str] = []
    for p in paragraphs:
        if len(p) <= max_size:
            units.append(p)
        else:
            units.extend(_split_sentences(p, max_size))

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for u in units:
        if buf_len + len(u) + 1 <= target_size:
            buf.append(u)
            buf_len += len(u) + 1
            continue
        # flush
        if buf:
            chunks.append("\n".join(buf).strip())
        # 새 buffer 시작 (overlap: 직전 chunk 꼬리)
        if chunks and overlap_size > 0:
            tail = chunks[-1][-overlap_size:]
            buf = [tail, u]
            buf_len = len(tail) + len(u) + 1
        else:
            buf = [u]
            buf_len = len(u)
        # 단일 unit이 target 초과시 그대로 flush
        if buf_len > max_size:
            chunks.append("\n".join(buf).strip())
            buf = []
            buf_len = 0
    if buf:
        chunks.append("\n".join(buf).strip())

    # 비거나 너무 짧은 chunk 제거
    return [c for c in chunks if len(c) >= 50]


def chunk_file(path: Path, *, source: str | None = None, **kwargs) -> list[Chunk]:
    text = path.read_text(encoding="utf-8", errors="replace")
    src = source if source is not None else path.stem
    pieces = chunk_text(text, **kwargs)
    return [
        Chunk(source=src, chunk_id=i, text=t, char_len=len(t))
        for i, t in enumerate(pieces)
    ]


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--target", type=int, default=700)
    ap.add_argument("--max", type=int, default=1000)
    ap.add_argument("--overlap", type=int, default=120)
    args = ap.parse_args()

    chunks = chunk_file(
        args.path,
        target_size=args.target,
        max_size=args.max,
        overlap_size=args.overlap,
    )
    print(f"[{args.path.name}] chunks={len(chunks)}  total_chars={sum(c.char_len for c in chunks)}")
    for c in chunks[:3]:
        print(f"--- chunk {c.chunk_id} ({c.char_len} chars) ---")
        print(c.text[:200])
