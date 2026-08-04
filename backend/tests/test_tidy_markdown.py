"""답변 형식 정리(_tidy_markdown) 불변식 — 구분선·과다 빈줄만 제거하고 내용은 무손실.

[계기 2026-07-27] '---'·불필요 줄바꿈이 LLM 재생성(보강/교정)으로만 정리돼, 형식 정리가
내용-변경 재생성과 묶여 있었다(운영자 지적: 정리되면서 내용이 삭감되는 듯). 결정적 스크럽으로
분리한다. ★이 함수는 절대 '내용 글자'를 지우면 안 된다(형식 기호만).
"""
from __future__ import annotations

from backend.app.services.chat_service import _tidy_markdown


def test_removes_hr_lines_keeps_content() -> None:
    src = "### 제목\n본문 첫 문단입니다.\n\n---\n\n둘째 문단입니다.\n***\n셋째 문단."
    out = _tidy_markdown(src)
    assert "본문 첫 문단입니다." in out
    assert "둘째 문단입니다." in out and "셋째 문단." in out
    assert "\n---\n" not in out and "***" not in out


def test_preserves_markdown_table_separator() -> None:
    """표 구분선(|---|)은 '|'가 있어 지우면 안 된다(HR 아님)."""
    src = "| 월 | 운세 |\n|---|---|\n| 1월 | 길 |"
    out = _tidy_markdown(src)
    assert "|---|---|" in out and "| 1월 | 길 |" in out


def test_preserves_inline_hyphens() -> None:
    """문장 안 하이픈(범위표기 2020-2021)은 구분선이 아니므로 보존."""
    out = _tidy_markdown("기간은 2020-2021년입니다. 값은 A--B 범위.")
    assert "2020-2021" in out and "A--B" in out


def test_collapses_excess_blank_lines_no_content_loss() -> None:
    src = "첫 줄.\n\n\n\n둘째 줄."
    out = _tidy_markdown(src)
    assert out == "첫 줄.\n\n둘째 줄."


def test_char_count_never_drops_below_content() -> None:
    """형식 기호만 빠지므로, 한글 내용 글자 수는 보존돼야 한다(삭감 금지 불변식)."""
    src = "성실하고 책임감 있는 분입니다.\n\n---\n\n올해는 재물운이 좋습니다."
    def _hangul(s: str) -> int:
        return sum(1 for c in s if "가" <= c <= "힣")
    assert _hangul(_tidy_markdown(src)) == _hangul(src)


# ── 교정/보강 게이트 삭감 방지 불변식(2026-07-27) ──────────────────────────────
from backend.app.services.chat_service import _safe_replace


def _para(n: int) -> str:
    base = "당신은 성실하고 책임감 있는 분이며 올해는 재물운이 좋습니다. "
    return (base * (n // len(base) + 1))[:n].rstrip() + " 좋은 한 해가 되시길 바랍니다."


def test_correction_gate_blocks_large_shrink() -> None:
    """교정/보강 교체는 원본의 30~40%를 지우면 거부돼야 한다(운영자 지적: 검증 후 내용 삭감).

    옛 min_ratio=0.6 은 40% 삭감본을 통과시켰다 → 0.85(교정)·0.9(보강)로 조임."""
    orig = _para(1000)
    assert _safe_replace(orig, _para(700), min_ratio=0.85) is None   # 30% 삭감 → 거부
    assert _safe_replace(orig, _para(600), min_ratio=0.85) is None   # 40% 삭감 → 거부
    assert _safe_replace(orig, _para(950), min_ratio=0.85) is not None  # 5% 소폭 → 허용
    # 보강(0.9)은 더 엄격 — 15% 삭감도 거부
    assert _safe_replace(orig, _para(850), min_ratio=0.9) is None


def test_correction_gate_not_regressed_to_lenient() -> None:
    """호출부가 다시 0.6/0.75 로 느슨해지지 않도록 소스에 강한 게이트가 있는지 확인."""
    import io, pathlib
    src = io.open(pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "chat_service.py",
                  encoding="utf-8").read()
    assert "min_ratio=0.85" in src, "교정 게이트(0.85)가 사라졌습니다 — 40% 삭감 재발"
    assert src.count("min_ratio=0.9") >= 3, "보강 게이트(0.9) 3곳이 유지돼야 합니다"
    assert "_safe_replace(cur, new.strip(), min_ratio=0.6)" not in src, "옛 교정 게이트(0.6) 복귀 금지"
