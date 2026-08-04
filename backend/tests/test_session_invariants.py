# -*- coding: utf-8 -*-
"""2026-07-22 전수감사가 만든 **깨지기 쉬운 불변식** 잠금.

이 파일의 목적은 기능 검증이 아니라 **되돌림 방지**다. 여기 있는 것들은 전부
'코드만 보면 정리하고 싶어지는데 정리하면 조용히 사고가 나는' 자리이고,
주석만으로는 부족해서(주석은 지워진다) 테스트로 못박는다.

배경: 불변식 색출(51에이전트)이 치명 6건·큼 40건을 찾았는데 그 중 다수가 무잠금이었다.
특히 '두 줄의 순서' 같은 것은 값이 아니라 배치가 성질이라 기존 테스트로는 절대 안 잡힌다 —
실제로 순서를 뒤집은 변종을 만들어 돌려 보니 638개 테스트가 전부 통과했다.

⛔ 이 파일의 테스트를 지우거나 완화하려면 운영자 승인을 받으세요.
   관련: docs/rag_hallucination_audit_2026-07-22.md
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


class _Vec(list):
    """실코드가 embedder 출력에 .tolist() 를 부르므로 흉내낸다."""
    def tolist(self):
        return list(self)


class _FakeEmbedder:
    def encode(self, *a, **k):
        return [_Vec([0.0, 0.0])]


# ══════════════════════════════════════════════════════════════════════
# 1. 리랭커 임계는 tier 가중치를 **더하기 전** 원점수로 판정한다
# ══════════════════════════════════════════════════════════════════════
def test_rerank_threshold_applied_before_tier_boost():
    """두 줄을 합치면(`p = raw + boost` 후 임계 비교) 무관 자료가 유료 답변 근거로 들어간다.

    운영값이 이 순서를 load-bearing 으로 만든다 — tier1 boost 0.12 > rerank_min_score 0.1.
    즉 리랭커 관련도 **0.00(완전 무관)** 인 tier1 청크가 임계를 넘어 [참고자료]가 된다.
    그러면 '자료가 없으면 0건 → LLM 단독'이라는 설계된 안전 폴백이 통째로 사라지고,
    EVIDENCE_PRIORITY_RULE 이 '이 자료를 우선 따르라'고 지시한다.
    반환 score 는 리랭커 점수가 아니라 원본 코사인이라 로그로도 티가 안 나는 무증상 사고다.
    """
    from ml.inference.retriever import SajuRetriever

    class _Hit:
        def __init__(self, text, score, tier):
            self.payload = {"text": text, "source": "s", "chunk_id": 0, "trust_tier": tier}
            self.score = score

    class _Pts:
        def __init__(self, pts):
            self.points = pts

    class _Client:
        def query_points(self, **kw):
            # dense 는 통과하지만 리랭커가 '무관'으로 판정할 tier1 청크 하나
            return _Pts([_Hit("무관한 tier1 자료", 0.90, 1)])

    class _Reranker:
        def predict(self, pairs):
            return [0.0] * len(pairs)      # 관련도 0.00 — 어떤 임계도 넘으면 안 된다

    r = SajuRetriever.__new__(SajuRetriever)
    r.client = _Client()
    r.collection = "c"
    r.embedder = _FakeEmbedder()
    r.pdf_boost = 0.0
    r.over_fetch = 4
    r.reranker_model = "stub"
    r.reranker_device = "cpu"
    r._reranker_obj = _Reranker()

    got = r.search("q", top_k=4, rerank=True, rerank_min_score=0.1,
                   tier_boosts={1: 0.12, 2: 0.06, 3: 0.0})
    assert got == [], (
        "관련도 0.00 인 청크가 tier 가중치(0.12)로 임계(0.1)를 넘었다 — "
        "임계 판정과 가중치 가산의 순서가 뒤집혔다")


def test_dense_min_score_applies_in_rerank_branch():
    """dense 하한은 리랭커 경로에서도 적용된다(비리랭커 분기와 **의도적 중복**).

    이게 빠지면 저관련 후보가 리랭커까지 흘러가 통과할 여지가 생긴다.
    P0 이전에는 이 줄이 없어 min_score 를 0.99 로 올려도 결과가 동일했다."""
    from ml.inference.retriever import SajuRetriever

    class _Hit:
        def __init__(self, s):
            self.payload = {"text": "t", "source": "s", "chunk_id": 0, "trust_tier": 2}
            self.score = s

    class _Client:
        def query_points(self, **kw):
            return type("P", (), {"points": [_Hit(0.30)]})()      # dense 0.30 < 0.45

    r = SajuRetriever.__new__(SajuRetriever)
    r.client = _Client()
    r.collection = "c"
    r.embedder = _FakeEmbedder()
    r.pdf_boost = 0.0
    r.over_fetch = 4
    r.reranker_model = "stub"
    r.reranker_device = "cpu"
    r._reranker_obj = type("R", (), {"predict": lambda self, pairs: [0.99] * len(pairs)})()

    got = r.search("q", top_k=4, min_score=0.45, rerank=True, rerank_min_score=0.1)
    assert got == [], "dense 하한이 리랭커 분기에서 적용되지 않았다"


# ══════════════════════════════════════════════════════════════════════
# 2. 예시명식 판정 — 그리드 검사가 마커 검사보다 **먼저**
# ══════════════════════════════════════════════════════════════════════
def test_grid_check_runs_before_marker_gate():
    """마커('예시','사례')가 **없어도** 4주 그리드만으로 예시로 판정되어야 한다.

    교재·상담기록은 '예시' 같은 말 없이 표만 나열한다. 마커 검사를 앞 가드로 올리면
    마커 없는 4주 그리드(전수 1,823건 중 1,651건)가 통째로 빠져 P0 의
    '타인 명식 16.6% → 0.00%' 가 조용히 원상복구된다.
    ⚠️기존 테스트(test_p3_rag_coverage)의 입력은 둘 다 마커 경로로만 통과하므로
      순서를 뒤집어도 잡지 못한다 — 그래서 이 테스트가 따로 필요하다."""
    from ml.data_pipeline.tagging import is_example_chunk

    no_marker_grid = "甲 乙 丙 丁\n子 丑 寅 卯\n이 명식을 보면 재성이 강하다."
    assert "예시" not in no_marker_grid and "사례" not in no_marker_grid
    assert is_example_chunk(no_marker_grid), "마커 없는 4주 그리드를 놓쳤다 — 검사 순서가 뒤집혔다"


def test_grid_requires_branch_row_near_stem_row():
    """천간행 단독은 명식이 아니다 — 직후 2줄 안에 지지행이 있어야 한다.

    조건을 없애면 '甲 乙 丙 丁은 양간이다' 같은 이론 문장이 예시로 오판된다.
    반대로 창을 문서 전체로 넓히면 천간표와 지지표가 떨어져 있는 이론서(천간론·지지론)가
    통째로 걸린다 — 그리고 is_example 은 신규 색인에서 **검역(미색인)** 이라
    (ml/data_pipeline/quarantine.py:33) 원자료가 코퍼스에 아예 안 들어간다."""
    from ml.data_pipeline.tagging import has_four_pillar_grid

    assert not has_four_pillar_grid("甲 乙 丙 丁\n이들은 모두 양간이다.")
    assert has_four_pillar_grid("甲 乙 丙 丁\n子 丑 寅 卯")          # 1줄 뒤
    assert has_four_pillar_grid("甲 乙 丙 丁\n(표)\n子 丑 寅 卯")     # 2줄 뒤
    # 3줄 뒤는 의도적으로 안 잡는다(상한) — 넓히면 이론서가 미색인된다
    assert not has_four_pillar_grid("甲 乙 丙 丁\n산문1\n산문2\n子 丑 寅 卯")


def test_grid_row_width_is_capped_at_four():
    """행 길이 2~4칸만 명식으로 본다 — 10간·12지 전체 나열은 이론표이지 명식이 아니다."""
    from ml.data_pipeline.tagging import has_four_pillar_grid

    assert not has_four_pillar_grid(
        "甲 乙 丙 丁 戊 己 庚 辛 壬 癸\n子 丑 寅 卯 辰 巳 午 未 申 酉 戌 亥")


def test_korean_ratio_denominator_keeps_latin():
    """분모에서 빼는 것은 공백·숫자·구두점뿐 — 라틴 문자는 남아야 비율 규칙이 산다.

    라틴까지 분모에서 빼면 OCR 이 깨져 영문 난수열이 된 청크가 '한글 비율 100%'가 된다."""
    from ml.data_pipeline.tagging import korean_ratio

    assert korean_ratio("가나다 PPpoeerpop") < 0.5, "라틴 문자가 분모에서 빠졌다"
    # 표 형식 정상 자료는 살아야 한다(숫자·구두점은 분모에서 제외)
    assert korean_ratio("이 지 오 7 9 8 양양음") > 0.8


# ══════════════════════════════════════════════════════════════════════
# 3. 아호 — 작명 경로로 흘러가면 안 된다
# ══════════════════════════════════════════════════════════════════════
def test_aho_never_routes_through_baby_naming_engine():
    """kind=='aho' 가 recommend_names 로 흘러가면 신생아 이름이 다시 나온다."""
    src = (ROOT / "backend" / "app" / "services" / "tool_service.py").read_text(encoding="utf-8")
    m = re.search(r'elif kind == "aho":(.*?)else:  # jakmyeong', src, re.S)
    assert m, "아호 분기가 사라졌다 — recommend_names 로 되돌아갔을 수 있다"
    # 주석에는 경위 설명으로 recommend_names 가 등장하므로 **호출**만 본다
    body = "\n".join(ln for ln in m.group(1).splitlines() if not ln.strip().startswith("#"))
    assert "naming_engine.recommend_aho(" in body
    assert "naming_engine.recommend_names(" not in body, \
        "아호가 신생아 작명 엔진으로 되돌아갔다"


def test_aho_render_dispatch_exists():
    """작명 렌더러는 c['suri_grade'] 를 무조건 참조하는데 AhoCandidate 에는 그 필드가 없다 —
    분기를 지우면 아호 해설이 KeyError 로 죽는다."""
    from backend.app.saju.naming import AhoCandidate
    from backend.app.services import tool_service as T

    assert "suri_grade" not in AhoCandidate.model_fields
    assert hasattr(T, "_render_aho")
    src = (ROOT / "backend" / "app" / "services" / "tool_service.py").read_text(encoding="utf-8")
    assert 'if kind == "aho":\n        return _render_aho(r)' in src


def test_aho_bad_reading_list_not_emptied():
    """일상어 동음 차단 목록이 비면 국자·창자·서자가 유료 리포트에 실린다."""
    from backend.app.saju import naming as N

    assert len(N._AHO_BAD_READING) >= 40
    for w in ("국자", "창자", "청각", "서자"):
        assert w in N._AHO_BAD_READING


def test_aho_data_files_load_nonempty():
    """_load_json 이 예외를 삼켜 {} 를 돌려주면 후보가 0건이 되고, 빈 후보표는
    _verify_naming_candidates 가 조용히 통과시켜(`if not cands: return []`)
    LLM 이 지어낸 아호가 검증 없이 나간다."""
    from backend.app.saju import naming as N

    assert len(N.aho_lexicon()) >= 50
    assert len(N.aho_types().get("types") or []) == 4
    assert len(N.aho_examples()) >= 10


def test_aho_still_covered_by_naming_verifiers():
    """아호는 후보표 밖 한자 창작('準晙' 실측)과 오행 뒤섞기의 최대 피해 메뉴다 —
    전용 엔진으로 분리한 뒤에도 검증기 대상에 남아 있어야 한다."""
    src = (ROOT / "backend" / "app" / "services" / "tool_service.py").read_text(encoding="utf-8")
    m = re.search(
        r'if rj\.get\("kind"\) in \(([^)]*)\):\s*\n\s*return \[lambda t: _verify_naming_candidates',
        src)
    assert m, "작명 검증기 등록 지점을 찾지 못했다"
    assert '"aho"' in m.group(1), "아호가 작명 검증기 대상에서 빠졌다"


# ══════════════════════════════════════════════════════════════════════
# 4. 평가 — 라이브 GPU 를 건드리면 안 된다
# ══════════════════════════════════════════════════════════════════════
def test_manual_eval_runs_in_subprocess_with_gpu_disabled():
    """인프로세스로 되돌리면 평가가 ollama·리랭커의 GPU1 을 잡아 OOM 이 난다
    (실측 여유 1,129MiB / BGE-m3 약 2.3GB)."""
    src = (ROOT / "backend" / "app" / "api" / "eval.py").read_text(encoding="utf-8")
    assert "subprocess.run" in src
    assert 'env["CUDA_VISIBLE_DEVICES"] = "-1"' in src
    assert not re.search(r"^\s*(result\s*=\s*)?evaluate\(", src, re.M),         "인프로세스 evaluate() 호출이 되살아났다"


def test_eval_forces_cpu_regardless_of_ops_setting():
    """운영 설정을 읽어오더라도 device 만은 CPU 로 고정한다 — 라이브 GPU 보호."""
    src = (ROOT / "ml" / "eval" / "eval_retrieval.py").read_text(encoding="utf-8")
    assert 'dev = "cpu"' in src
    assert "reranker_device=dev" in src


def test_eval_summary_records_mode_and_gate():
    """/trend 가 이 값으로 추세 단절선을 긋는다 — 빠지면 정렬 전후를 섞어 보고 오독한다."""
    src = (ROOT / "ml" / "eval" / "eval_retrieval.py").read_text(encoding="utf-8")
    for key in ('"eval_mode"', '"gate"', '"zero_hit_rate"', '"mean_chunks_returned"'):
        assert key in src, f"runs.jsonl 요약에서 {key} 가 빠졌다"


def test_trend_compares_by_measurement_mode_not_sample_size():
    """비교 기준이 N 으로 되돌아가면 '옛측정'과 '운영정렬'을 한 선에 그리게 된다."""
    src = (ROOT / "frontend" / "src" / "pages" / "TrendPage.tsx").read_text(encoding="utf-8")
    assert "function evalMode(" in src
    assert "evalMode(runs[j]) === evalMode(runs[i])" in src


# ══════════════════════════════════════════════════════════════════════
# 5. 층 경계 — 자료 주입 경로가 갈라지면 안 된다
# ══════════════════════════════════════════════════════════════════════
def test_rag_context_block_returns_none_when_empty():
    """0건에 빈 문자열을 돌려주면 호출부의 `has_sources=bool(rag_ctx)` 가 False 로 뒤집혀
    '자료 우선' 지시가 사라지고, 반대로 문자열을 돌려주면 유령 지시가 붙는다."""
    from backend.app.services.chat_service import rag_context_block

    assert rag_context_block([]) is None


def test_new_verifiers_registered_in_both_gate_and_correction_loop():
    """게이트에만 꽂고 교정 루프에 안 꽂으면 교정 후 재검증에서 빠져 무한히 통과한다."""
    src = (ROOT / "backend" / "app" / "services" / "chat_service.py").read_text(encoding="utf-8")
    for fn in ("_verify_pillar_stems", "_verify_twelve_life", "_verify_whole_chart"):
        assert src.count(f"{fn}(") >= 3, f"{fn} 가 게이트·교정 루프 양쪽에 등록되지 않았다"


def test_last_chunks_trace_recorded():
    """검증 flag 미해소 시 오염원 문서를 역추적하는 유일한 경로다."""
    src = (ROOT / "backend" / "app" / "services" / "chat_service.py").read_text(encoding="utf-8")
    assert "_LAST_CHUNKS.set(" in src
    assert "_rag_trace()" in src


@pytest.mark.parametrize("path,needle", [
    ("backend/app/services/tool_service.py", "chart_reconfirm_block"),
    ("backend/app/services/compat_service.py", "chart_reconfirm_block"),
    ("backend/app/api/dream.py", "chart_reconfirm_block"),
])
def test_chart_guard_present_in_rag_paths(path, needle):
    """RAG 가 사용자 프롬프트의 38~86%를 차지하는 경로에 명식 재확인 가드가 있어야 한다."""
    assert needle in (ROOT / path).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# 6. 교차 세션(2026-07-22) — 두 작업이 부딪힌 자리
# ══════════════════════════════════════════════════════════════════════
def test_dream_followup_declares_symbol_dictionary_as_source():
    """꿈해몽 후속질문 브리핑에는 상징 사전이 실린다. 그런데 has_sources 를 rag_ctx 로만
    판정하면 해몽 RAG 가 실질 0건이라 거의 항상 '참고자료가 없습니다'가 붙는다 —
    **브리프에는 자료가 있는데** 없다고 지시하는 자기모순이다(실 세션 재현)."""
    src = (ROOT / "backend" / "app" / "services" / "tool_service.py").read_text(encoding="utf-8")
    assert "_brief_has_sources" in src
    assert src.count("has_sources=bool(rag_ctx or _brief_has_sources)") >= 2, \
        "해설·추가질문 양쪽 모두에서 브리프 자료를 반영해야 한다"


def test_refine_paths_declare_absence_of_sources():
    """P3-E1 을 chat 시스템프롬프트에만 넣고 보강·폴백 경로에는 안 넣었다.
    '참고자료에 비추어 검증하라'가 0건일 때 유령 지시가 되어 문헌명을 지어내게 만든다."""
    from backend.app.services.chat_service import refine_system_for

    base = "기본 지시"
    assert refine_system_for(base, "자료 있음") == base
    out = refine_system_for(base, None)
    assert out != base and "주어지지 않았습니다" in out
    assert "지어내지 마세요" in out

    ext = (ROOT / "backend" / "app" / "services" / "external_llm.py").read_text(encoding="utf-8")
    assert ext.count("_sys_for(") >= 5, "외부 LLM 보강·생성 4경로 + 헬퍼 정의"
    assert "system=_REFINE_SYSTEM," not in ext and "system=_GENERATE_SYSTEM," not in ext

    chat = (ROOT / "backend" / "app" / "services" / "chat_service.py").read_text(encoding="utf-8")
    assert '"content": _QWEN_REFINE_SYSTEM' not in chat, "qwen 보강도 조건부여야 한다"


@pytest.mark.parametrize("text,should_match", [
    ("#### 1월: 기축월", True),
    ("- **3월** 어쩌고", True),
    ("- 4월", True),               # 새 서식 규칙이 유도하는 형태
    ("- 4월:", True),
    ("- 4월 기축월", True),
    ("- 4월(己丑月)", True),
    ("- 3월 전후로 큰 결정을 하게 됩니다", False),   # 본문 불릿 — 잡으면 섹션이 조각난다
    ("- 5월에는 이런 일이", False),
    ("- 6월과 7월 사이에 변화가", False),
    ("평문 8월 어쩌고", False),
])
def test_month_head_covers_plain_bullet_without_false_positives(text, should_match):
    """서식 규칙이 '- ' 불릿을 권장하게 바뀌어 굵게 없는 '- 4월'이 사각지대가 됐다.
    그렇다고 공백만 와도 인정하면 본문 불릿까지 헤딩이 되어 월별 백스톱이 섹션을 파괴한다."""
    from backend.app.services.chat_service import _MONTH_HEAD_RE

    assert bool(list(_MONTH_HEAD_RE.finditer(text))) is should_match


def test_wuxing_eight_basis_is_locked():
    """[다른 세션 변경 잠금] 팔자8 기준을 잠그는 테스트가 0건이라 chart.wuxing 으로 되돌려도
    전체 테스트가 통과했다. 합계 불변식(시 있으면 8, 시 모름 6)으로 못박는다."""
    from datetime import date

    from backend.app.saju.engine import build_chart
    from backend.app.saju.types import BirthInput, CalendarType, Gender
    from backend.app.saju.wuxing import wuxing_eight_of

    ch = build_chart(BirthInput(birth_date=date(1985, 3, 15), birth_time="09:30",
                                calendar=CalendarType.SOLAR, gender=Gender.MALE))
    e = wuxing_eight_of(ch)
    assert sum([e.wood, e.fire, e.earth, e.metal, e.water]) == 8, "팔자 8글자 기준이 깨졌다"
    # full(지장간 포함)과는 반드시 달라야 한다 — 같으면 둘 중 하나가 잘못 계산된 것이다
    w = ch.wuxing
    assert sum([w.wood, w.fire, w.earth, w.metal, w.water]) > 8

    no_hour = build_chart(BirthInput(birth_date=date(1985, 3, 15), birth_time=None,
                                     calendar=CalendarType.SOLAR, gender=Gender.MALE))
    e2 = wuxing_eight_of(no_hour)
    assert sum([e2.wood, e2.fire, e2.earth, e2.metal, e2.water]) in (6, 8)


def test_wuxing_eight_survives_legacy_chart_json():
    """옛 저장 chart_json 에는 wuxing_eight 필드가 없다 — pillars 로 재계산돼야 한다."""
    from datetime import date

    from backend.app.saju.engine import build_chart
    from backend.app.saju.types import BirthInput, CalendarType, Gender
    from backend.app.saju.wuxing import wuxing_eight_ko_from_json

    cj = build_chart(BirthInput(birth_date=date(1990, 11, 2), birth_time="09:30",
                                calendar=CalendarType.SOLAR, gender=Gender.FEMALE)).model_dump(mode="json")
    cj.pop("wuxing_eight", None)          # 구 스키마 재현
    got = wuxing_eight_ko_from_json(cj)
    assert got and sum(got.values()) == 8


# ══════════════════════════════════════════════════════════════════════
# 7. 스캔 전사본 명식 탐지 (2026-07-22 오늘의운세 오염)
# ══════════════════════════════════════════════════════════════════════
def test_grid_detects_ideographic_space():
    """스캔 전사본(vision-transcribed)은 거의 전부 **전각공백(U+3000)** 으로 열을 나눈다.
    구분자에 이게 빠져 있어 「공재와 사재의 구별」(乾命 67세)·「재다신약」(坤命 54세) 같은
    개인 감명문이 검색 1순위로 올라와 오늘의운세 답변 근거가 됐다(실측 3/3 세션)."""
    from ml.data_pipeline.tagging import has_four_pillar_grid

    assert has_four_pillar_grid("丁　庚　甲　庚\n亥　寅　申　子")


def test_grid_allows_row_end_label():
    """`$` 앵커라 줄 끝 라벨이 붙으면 매치가 깨졌다 — 사례집은 라벨을 행 끝에 단다."""
    from ml.data_pipeline.tagging import has_four_pillar_grid

    assert has_four_pillar_grid("甲　乙　丙　丁\n子　丑　寅　卯 乾命")
    assert has_four_pillar_grid("甲 乙 丙 丁\n子 丑 寅 卯 (남자사주)")


def test_grid_requires_equal_column_count():
    """천간 열 수와 지지 열 수가 같아야 4주다. 이 검사가 없으면 tier1 「간지와 육친」의
    **오행 배치도**('丙　丁' 2열 / '巳　午　未' 3열)가 명식으로 오탐된다."""
    from ml.data_pipeline.tagging import has_four_pillar_grid

    assert not has_four_pillar_grid("丙　丁\n巳　午　未")
    assert has_four_pillar_grid("丙　丁\n巳　午")


def test_labeled_chart_signal_scope():
    """성별 라벨 신호의 채택 범위 — 넓히면 교리가 통째로 검역된다(미색인).

    ⛔男命·女命·(男)·(女)는 정밀도 20%로 기각됐다: 117건 중 74건이 60갑자 일주 사전이고
    tier1 「육친」 정의표('편관·정관: (女)남편 / (男)자식')까지 걸린다."""
    from ml.data_pipeline.tagging import has_labeled_chart

    from ml.data_pipeline.tagging import is_example_chunk

    # 라벨이 명식 줄에 붙은 형태 — 라벨 경로가 잡는다
    assert has_labeled_chart("辛 辛 壬 丁\n卯 亥 寅 酉 (남자사주)")
    # 라벨이 별도 줄인 형태 — 라벨 경로는 못 잡지만 **그리드 경로**가 잡는다.
    # 두 경로가 함께 있어야 이 유형이 걸린다는 뜻이라 게이트 전체로 확인한다.
    sep_line = "丁　庚　甲　庚\n亥　寅　申　子\n乾命 2026년 67세"
    assert not has_labeled_chart(sep_line)
    assert is_example_chunk(sep_line), "전각공백 명식 + 별도줄 라벨을 게이트가 놓쳤다"
    # 男命/女命 은 신호가 아니다 — 일주 사전이 통째로 걸린다
    assert not has_labeled_chart("○ 癸酉일주 — 女命은 夫宮이 좋지 않아 늦게 만나는 것이 낫다")
    # 명식 없이 라벨만 있는 강의 제목은 제외
    assert not has_labeled_chart("[법오통변 1] 坤命 이혼녀 — 일주 물상에 비추어 보면")


def test_labeled_chart_exempts_naming_lecture():
    """성명사주학 강의는 육친명에 맞춰 **지어낸 예시 인물**로 원리를 가르치는 교재다.
    26건이 통째로 오탐돼 작명·개명 근거가 고갈된다."""
    from ml.data_pipeline.tagging import has_labeled_chart

    t = "5) 원국육친 산출예문 (1) 1970년 庚戌生 乾命 김우혁 / 천간 원국육친 甲 乙 丙"
    assert has_labeled_chart(t)                      # 소스 없으면 걸린다
    assert not has_labeled_chart(t, "u00694_성명사주학01")   # 소스 예외로 보존
