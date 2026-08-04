# -*- coding: utf-8 -*-
"""집중·후속 단일질문(요점만) 분리 — 여지(num_predict) 캡 + 낮은 바닥으로 패딩·반복 억제.

운영자 지적(2026-08-03): '성격 어때?' 같은 단일 후속에 앞말 반복·장황. 원인=동시 병합 num_predict 6144↑
가 1차 생성부터 늘어지고 focused 바닥(1500/1800)이 억지 분량 강제. 종합은 풍부하게 두고 집중만 요점화.
"""
from __future__ import annotations

import io
import pathlib

from backend.app.services.chat_service import _FOCUSED_NUM_PREDICT, _focused_floor

_SRC = io.open(pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "chat_service.py",
               encoding="utf-8").read()


def test_focused_floor_values():
    # 400~800은 과소(운영자) → 밀도형 바닥은 그보다 위, 종합(3000/3500)보다는 아래.
    assert _focused_floor("deep") == 1100
    assert _focused_floor("easy") == 950
    for d in ("deep", "easy", "normal"):
        assert 800 < _focused_floor(d) < 1500


def test_focused_num_predict_cap_is_below_global():
    # 종합 여지(6144)의 절반 수준으로 1차 생성 늘어짐을 캡.
    assert _FOCUSED_NUM_PREDICT == 3072


def test_focused_cap_wired_in_both_paths():
    # 비스트림(_call_ollama)·스트림(_stream_ollama) 1차 생성 모두 focused면 캡을 넘긴다.
    assert _SRC.count("_FOCUSED_NUM_PREDICT if _is_narrow") >= 2, "focused num_predict 캡이 두 경로에 배선 안 됨"
    # 두 경로 floor가 _focused_floor(depth)로 낮춰졌다(억지 재생성 패딩 방지).
    assert _SRC.count("_focused_floor(depth)") >= 2, "focused 바닥 하향이 두 경로에 반영 안 됨"
    # 종합 답변 바닥(s.answer_min_chars)은 그대로 유지(병합의 분량확대 의도 보존).
    assert "s.answer_min_chars_deep if depth" in _SRC
