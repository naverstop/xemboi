# -*- coding: utf-8 -*-
"""P3 — RAG 커버리지·관측 회귀 테스트.

전수조사에서 드러난 것: 같은 증상(0건·근거 빈약)이라도 원인이 쿼리/자료/임계/관측으로 갈리고
처방이 정반대다. 여기서는 **코드로 고친 것**만 고정한다(자료 확보는 운영자 결정 사항).
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender


# ── D-1 회수 로깅: 유료 본해설(message="")도 기록되어야 한다 ──────────────
def test_search_corpus_logs_even_without_question(monkeypatch):
    """예전에는 `if question:` 이라 message="" 인 본해설 경로가 통째로 미기록이었다.

    프론트가 본해설을 message="" 로 보내므로, 이 조건 때문에 **정작 유료 답변의 회수 품질만**
    로그에 안 남았다(tool 세션 327건 중 19.9%, 꿈해몽 0/29). 관측 없이는 쿼리를 고쳐도
    좋아졌는지 확인할 수 없어 P3 의 선행 작업으로 뚫었다."""
    from backend.app.services import chat_service as C

    logged: list[dict] = []
    monkeypatch.setattr(C, "_log_retrieval",
                        lambda sid, q, k, ch, menu=None: logged.append(
                            {"sid": sid, "q": q, "menu": menu}))

    class _R:
        def search(self, *a, **kw):
            return []
    monkeypatch.setattr(C, "_get_retriever", lambda: _R())

    C._search_corpus("아무 쿼리", 4, session_id="s1", question=None, menu="naming/jakmyeong")
    assert len(logged) == 1
    assert logged[0]["menu"] == "naming/jakmyeong"
    assert "[explain]" in logged[0]["q"], "질문이 없으면 본해설 태그로 남아야 한다"


def test_search_corpus_keeps_user_question(monkeypatch):
    """추가질문 경로는 원래대로 사용자 질문을 그대로 기록한다."""
    from backend.app.services import chat_service as C

    logged: list[dict] = []
    monkeypatch.setattr(C, "_log_retrieval",
                        lambda sid, q, k, ch, menu=None: logged.append({"q": q, "menu": menu}))

    class _R:
        def search(self, *a, **kw):
            return []
    monkeypatch.setattr(C, "_get_retriever", lambda: _R())

    C._search_corpus("q", 4, question="올해 이직운은?", menu="chat")
    assert logged[0]["q"] == "올해 이직운은?"
    assert logged[0]["menu"] == "chat"


def test_retrieval_log_has_menu_column():
    """메뉴 태그가 없으면 세션이 지워진 뒤 추적이 끊긴다(전기간 orphan 39%)."""
    from backend.app.repositories.models import RetrievalLog
    assert "menu" in RetrievalLog.__table__.columns


# ── A-1 궁합 쿼리: 표가 아니라 '무엇을 묻는지'가 들어가야 한다 ─────────────
@pytest.fixture(scope="module")
def compat_pair():
    a = build_chart(BirthInput(birth_date=date(1990, 5, 3), birth_time="10:00",
                               calendar=CalendarType.SOLAR, gender=Gender.FEMALE))
    b = build_chart(BirthInput(birth_date=date(1988, 11, 20), birth_time="14:00",
                               calendar=CalendarType.SOLAR, gender=Gender.MALE))
    return a, b


def test_compat_rag_query_contains_intent(compat_pair):
    """실세션 23건 전수에서 쿼리에 '궁합'도 상대방도 0글자였다 — brief[:600] 이 A 명식 표
    안에서 끝났기 때문이다(A 한 사람 요약만 1,197~1,418자). 이제는 반드시 들어가야 한다."""
    from backend.app.saju.compatibility import CompatResult
    from backend.app.services.compat_service import _rag_query

    a, b = compat_pair
    q = _rag_query(CompatResult.model_validate({"factors": {}, "perspectives": {}}), a, b)
    assert "궁합" in q
    # 두 사람의 일간이 모두 들어가야 '상대방이 없는' 옛 결함이 재발하지 않는다
    assert a.pillars.day.stem in q and b.pillars.day.stem in q
    assert len(q) <= 600


def test_compat_rag_query_prefers_user_question(compat_pair):
    """추가질문 경로는 원래 정상이었다 — 사용자 질문을 맨 앞에 그대로 둔다."""
    from backend.app.saju.compatibility import CompatResult
    from backend.app.services.compat_service import _rag_query

    a, b = compat_pair
    q = _rag_query(CompatResult.model_validate({"factors": {}, "perspectives": {}}),
                   a, b, "결혼 시기는 언제가 좋을까요?")
    assert q.startswith("결혼 시기는 언제가 좋을까요?")


# ── A-2 작명·아호 쿼리: 영문 Unihan 훈이 빠져야 한다 ──────────────────────
class _Row:
    def __init__(self, kind, result_json):
        self.kind = kind
        self.tool = "naming"
        self.result_json = result_json


_NAMING_RESULT = {
    "surname": "김", "deficient": ["水", "木"],
    "candidates": [{"given": "도현", "reading": "도현", "score": 93, "suri_grade": "길",
                    "elements": ["土"], "baleum_elements": ["火"],
                    "meaning": "have, own, possess; exist"}],
}


@pytest.mark.parametrize("kind", ["jakmyeong", "aho"])
def test_naming_rag_query_drops_english(kind):
    """쿼리의 34.8~36.7%가 라틴 문자였고 한글 산문 줄은 0개였다(코퍼스는 한글 54%·라틴 1%).
    후보표·영문 훈은 프롬프트(brief)에는 남고 **검색어에서만** 빠진다."""
    from backend.app.services.tool_service import _rag_query

    brief = "[작명 추천] 성: 김\n- 도현(도현) 93점 : have, own, possess; exist"
    q = _rag_query(_Row(kind, _NAMING_RESULT), brief)
    assert "possess" not in q and "own" not in q
    assert sum(1 for c in q if c.isascii() and c.isalpha()) == 0
    assert "부족 오행" in q or "부족오행" in q


def test_gaemyeong_query_unchanged():
    """⚠️개명은 이미 정상이었다(라틴 0%·절단 0/20건, 실측 회수 4건 max 0.674).
    '작명 메뉴 전체'로 일반화하면 멀쩡한 것을 망친다 — kind 분기를 고정한다."""
    from backend.app.services.tool_service import _rag_query

    brief = "[개명 진단] 현재 이름: 박민수(朴民秀) 수리 총격 29"
    assert _rag_query(_Row("gaemyeong", {}), brief) == brief


@pytest.mark.parametrize("kind", ["taekil", "calendar", "sinnyeon", "today"])
def test_other_menus_query_unchanged(kind):
    """택일·캘린더·신년은 형태가 표여도 실측 회수 4.00/4·0건률 0%(신년 max 0.708로 최고).
    지표가 없는 상태에서 선제 수정하면 개선인지 개악인지 알 수 없다 → 손대지 않는다."""
    from backend.app.services.tool_service import _rag_query

    brief = "[분석] 어떤 표\n행1\n행2"
    assert _rag_query(_Row(kind, {}), brief) == brief


# ── O-2 예시명식 판정: 교리 산문을 예시로 오판하지 않는다 ──────────────────
def test_is_example_keeps_doctrine_prose():
    """'예를 들어'·'사례'는 설명문의 일상 어휘이고, 조후·통근·합화 설명에는 간지 낱자가
    자연히 10~45자 섞인다. 낱자 8자 기준이 교리 244건을 검색에서 지웠다."""
    from ml.data_pipeline.tagging import is_example_chunk

    doctrine = ("예를 들어 음력 3월(辰月)의 甲木은 木의 기운이 강하고, 丁巳 시에 태어나면 "
                "火가 강해진다. 水와 火의 균형이 중요하다. 이런 사례가 조후의 기본이다.")
    assert not is_example_chunk(doctrine)


def test_is_example_still_catches_real_chart():
    """진짜 예시명식(간지 쌍 3개 이상 또는 4주 표기)은 그대로 걸려야 한다."""
    from ml.data_pipeline.tagging import is_example_chunk

    assert is_example_chunk("다음 사주를 보자. 년주 甲子 월주 丙寅 일주 戊辰 시주 庚申 남자 사주.")
    assert is_example_chunk("아래 사주 甲子 丙寅 戊辰 을 살펴보면 재성이 강하다.")


# ── D-2 평가 정렬: 운영 게이트를 그대로 쓴다 ─────────────────────────────
def test_eval_reads_ops_settings():
    """평가가 리랭커 off·게이트 off·top_k 8 로 돌아 운영(리랭커 on·게이트 3종·top_k 4)과
    다른 파이프라인을 쟀다. 후보 풀 17,746 vs 9,441 — 한 방향 과대평가였고, 그래서
    리랭커 분기의 버그를 33일간 못 잡았다."""
    from backend.app.core.config import get_settings
    from ml.eval.eval_retrieval import _ops_settings

    s = get_settings()
    ops = _ops_settings()
    assert ops, "운영 설정을 못 읽으면 평가가 다시 운영과 어긋난다"
    assert ops["top_k"] == max(1, min(s.rag_top_k_default, s.rag_max_top_k))
    assert ops["min_score"] == s.rag_min_score
    assert ops["rerank"] == s.rag_reranker_enabled
    assert ops["exclude_youtube"] == s.rag_exclude_youtube


# ── E-1 0건일 때 '자료를 따르라'가 붙으면 안 된다 ─────────────────────────
def test_expert_voice_rule_conditional():
    """0건이면 [참고자료] 블록이 통째로 사라지는데(rag_context_block([]) → None) '자료를 우선
    따르되'는 무조건 붙어 있었다 — 없는 자료를 따르라는 유령 지시라 근거를 지어낼 여지를 준다.
    실측 피해: 꿈해몽 저장본에 존재하지 않는 '꿈 해석 사전' 인용 2건."""
    from backend.app.services.chat_service import expert_voice_rule

    with_src = expert_voice_rule(True)
    no_src = expert_voice_rule(False)
    assert "자료를 우선 따르되" in with_src
    assert "자료를 우선 따르되" not in no_src
    assert "참고자료가 없습니다" in no_src
    # 화법 규칙(출처 언급 금지)은 자료 유무와 무관하게 항상 유지된다
    for r in (with_src, no_src):
        assert "'자료에 의하면'" in r and "절대 쓰지 마세요" in r


def test_compose_sys_content_threads_has_sources():
    from backend.app.services.chat_service import _compose_sys_content

    s1 = _compose_sys_content("SYS", "standard", "normal", has_sources=True)
    s0 = _compose_sys_content("SYS", "standard", "normal", has_sources=False)
    assert "자료를 우선 따르되" in s1 and "자료를 우선 따르되" not in s0
    assert "참고자료가 없습니다" in s0


def test_default_system_prompt_conditions_source_priority():
    """실제 활성 프롬프트는 template_service.DEFAULT_SYSTEM_PROMPT 다(DB 템플릿 0건).
    여기서도 '자료를 따르라'가 무조건문이면 조건부화가 반쪽이 된다."""
    from backend.app.services.template_service import DEFAULT_SYSTEM_PROMPT

    assert "주어진 경우" in DEFAULT_SYSTEM_PROMPT
    assert "참고자료가 없으면" in DEFAULT_SYSTEM_PROMPT


# ── E-3 chat 보강 경로가 공용 조립을 쓰는가 ──────────────────────────────
def test_no_manual_rag_context_assembly():
    """손 조립이 남아 있으면 그 경로만 EVIDENCE_PRIORITY_RULE(층 경계)이 빠진 채
    보강·폴백 LLM 으로 간다. 소스에서 직접 확인한다(런타임 경로가 길어 단위 호출이 어렵다)."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "backend" / "app" / "services" / "chat_service.py"
    text = src.read_text(encoding="utf-8")
    # 조립 코드는 rag_context_block 안에 **딱 한 번**만 있어야 한다(그게 유일한 조립처).
    # 출처명(출처:{c.source})은 앵무새 인용 차단(2026-08-03)으로 모델 컨텍스트에서 제거 — 본문만 조립.
    assert text.count("[자료{i}] {c.text}") == 1, \
        "참고자료 블록을 손으로 조립하는 곳이 또 있다 — 그 경로만 층 경계 규칙이 빠진다"
    assert text.count("rag_context_block(chunks)") >= 3


# ── E-4 꿈해몽 첫 풀이 가드 ──────────────────────────────────────────────
def test_dream_uses_shared_guard_chain():
    """dream.py 는 _compose_sys_content 를 안 거쳐 CHART_FIDELITY·EXPERT_VOICE·FACT_GROUNDING
    가드가 전부 빠져 있었다(저장본 50건 중 가짜 문헌 2건·명식 모순 3건)."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "backend" / "app" / "api" / "dream.py"
    text = src.read_text(encoding="utf-8")
    assert "_compose_sys_content(" in text
    assert "chart_reconfirm_block(" in text
    assert "_scrub_source_refs(" in text
    assert "_verify_myeongsik(" in text
