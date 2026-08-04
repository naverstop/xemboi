# -*- coding: utf-8 -*-
"""출력 품질 결함 3종 회귀 고정 (2026-07-21 신년운세 실측 — 운영자 지적).

① 잘림: ollama_num_predict 3072 → 신년운세(3,000자+12개월)가 5월 부근 중간 절단.
   → 전역 5120 + qwen 보강/교정 재생성은 초안 길이 기반 동적 확장 + 타임아웃 비례 연장.
② 한글(한글) 오병기: '정재(정재), 정인(정인)' — 한자 병기 자리에 한글 반복.
③ 중복 문장: 같은 문장이 문단 안에서 그대로 2회 반복(약한 LLM 루프).
②③은 fix_term_hanja 체인(전 메뉴 공통: chat/tool/compat + 저장본)에서 결정적으로 교정.
"""
from __future__ import annotations

from unittest.mock import patch

from backend.app.saju.constants import fix_term_hanja
from backend.app.services import chat_service as C

def _tool_stream_body(mod):
    """툴 스트림 '본문'을 돌려준다 — 공개 stream_message 는 과금 보상 래퍼라 본문 가드가 그 안에 없다.

    [2026-07-23] 스트림 예외 시 선차감 미환불을 고치면서 본문을 _stream_message_inner 로 옮겼다.
    래퍼가 없어지면 다시 stream_message 를 보므로, 구조가 바뀌어도 이 헬퍼만 유지되면 된다.
    """
    return getattr(mod, "_stream_message_inner", mod.stream_message)


# 스크린샷 실측 그대로의 결함 텍스트
_REAL = ("3월은 정재(정재), 정인(정인)이 강한 달로, 재물, 수입, 학습에 유리한 환경입니다. "
         "정재(정재)의 강한 기운은 재물과 수입에 대한 기회가 많을 수 있지만, 정인(정인)의 강한 기운은 "
         "학습, 교육, 지식 습득에 유리한 환경을 제공합니다. "
         "정재(정재)의 강한 기운은 재물과 수입에 대한 기회가 많을 수 있지만, 정인(정인)의 강한 기운은 "
         "학습, 교육, 지식 습득에 유리한 환경을 제공합니다.")


def test_hangul_hangul_paren_fixed():
    """'정재(정재)' → '정재(正財)' — 십성 전부."""
    out = fix_term_hanja(_REAL)
    assert "정재(정재)" not in out and "정인(정인)" not in out
    assert "정재(正財)" in out and "정인(正印)" in out


def test_duplicate_sentences_collapsed():
    """문단 안 완전 동일 문장(15자+) 반복은 1개로."""
    out = fix_term_hanja(_REAL)
    assert out.count("학습, 교육, 지식 습득에 유리한 환경을 제공합니다") == 1


def test_fix_chain_idempotent_and_safe():
    """멱등 + 간지 괄호·정상 병기·짧은 반복(구호 등)은 보존."""
    out = fix_term_hanja(_REAL)
    assert fix_term_hanja(out) == out
    keep = "용신(庚金)과 년주(癸巳), 정관(正官)은 그대로."
    assert fix_term_hanja(keep) == keep
    # [정책 확장 2026-07-21] 교차 문단 복붙('3월↔7월 같은 문장')도 제거 — 13메뉴 스모크 실측
    two_para = "이 달은 재물운이 좋아질 가능성이 있어요.\n이 달은 재물운이 좋아질 가능성이 있어요."
    assert fix_term_hanja(two_para).count("재물운이 좋아질") == 1
    # 짧은 반복(15자 미만 — 구호·라벨)은 어디서든 보존
    short = "행운의 색: 적색\n행운의 색: 적색"
    assert fix_term_hanja(short) == short


def test_bare_hanja_ten_god_gets_hangul():
    """십성 한자 단독('劫財') → '겁재(劫財)' 병기(라이브 스모크 실측). 병기·간지·복합한자는 불변."""
    out = fix_term_hanja("6월에는 '劫財'나 '傷官'와의 충돌이 있어 부담이 생길 수 있습니다.")
    assert "겁재(劫財)" in out and "상관(傷官)" in out and "'劫財'" not in out
    keep = "겁재(劫財)와 년주(癸巳)는 그대로."
    assert fix_term_hanja(keep) == keep
    compound = "고서 十神論에서 正財格이라 부른다."   # 붙은 한자열은 교정 대상 아님
    assert fix_term_hanja(compound) == compound


def test_chung_wonjin_bad_hanja_fixed():
    """오늘운세 실측 오병기 2건: 충(衝)→충(沖), 원진(原진)→원진(怨嗔). 일반어·정상병기 불변."""
    assert fix_term_hanja("겁재(劫財)와 충(衝)의 영향") == "겁재(劫財)와 충(沖)의 영향"
    assert fix_term_hanja("유(酉)와 원진(原진) 관계") == "유(酉)와 원진(怨嗔) 관계"
    for keep in ("충(沖)은 그대로", "충분(充分)한 검토", "원진(서로 꺼리는 관계)란"):
        assert fix_term_hanja(keep) == keep


def test_markdown_hr_stripped():
    """'---' 구분선 단독 줄 제거(실측: 렌더러 미지원으로 화면에 그대로 노출). 불릿·날짜·범위 보존."""
    t = "직업/일 운\n\n내용입니다.\n\n---\n\n재물 운\n***\n끝."
    out = fix_term_hanja(t)
    assert "---" not in out and "***" not in out and "재물 운" in out
    for keep in ("- 첫째 항목입니다", "2026-08-22 무진(戊辰)", "3~4개월"):
        assert fix_term_hanja(keep) == keep
    from backend.app.services.chat_service import CONSULTANT_STYLE_RULE, _QWEN_REFINE_SYSTEM
    assert "---" in CONSULTANT_STYLE_RULE and "---" in _QWEN_REFINE_SYSTEM  # 프롬프트 금지 명시


def test_easy_style_rule_attached_all_menus():
    """전 메뉴 시스템 프롬프트에 '쉬운 글' 공통 규칙 부착(오늘운세 술어나열 실측 재발 방지)."""
    from backend.app.services import tool_service as TS
    from backend.app.services.compat_service import COMPAT_SYSTEM
    for s in (TS.NAMING_SYSTEM, TS.TAEKIL_SYSTEM, TS.SINNYEON_SYSTEM, TS.TODAY_SYSTEM,
              TS.CALENDAR_SYSTEM, TS.AMULET_SYSTEM, TS.DREAM_SYSTEM, COMPAT_SYSTEM):
        assert "[쉬운 글 — 필수]" in s


def test_num_predict_default_raised():
    """전역 생성 상한 5120(3072로 되돌리면 신년운세 잘림 재발)."""
    from backend.app.core.config import Settings
    assert Settings.model_fields["ollama_num_predict"].default == 5120


def test_qwen_refine_num_predict_scales_with_draft():
    """qwen 보강은 초안 길이 기반으로 num_predict 확장(보강본 절단 방지)."""
    captured = {}
    def fake_call(msgs, model=None, temperature=None, num_predict=None):
        captured["np"] = num_predict
        return "보강된 답변입니다. 충분히 긴 한국어 문장으로 마무리합니다."
    long_draft = "가" * 6000
    s = C.get_settings()
    _old = s.deep_local_refine_enabled
    try:
        s.deep_local_refine_enabled = True   # 테스트 환경 기본 off → 켜고 검증
        with patch.object(C, "_call_ollama", fake_call):
            C._refine_with_qwen(question="q", draft=long_draft, saju_summary=None,
                                evidence=None, rag_context=None, dialect_instruction=None)
    finally:
        s.deep_local_refine_enabled = _old
    assert captured.get("np") and captured["np"] >= 7000  # 6000자 초안 → 7024


def test_correction_regen_num_predict_scales():
    """교정 재생성도 답변 길이 기반(고정 2048은 장문 절단) + 4096 캡(타임아웃 가드)."""
    captured = {}
    def fake_call(msgs, model=None, temperature=None, num_predict=None):
        captured.setdefault("nps", []).append(num_predict)
        return "여전히 일지 사(巳)"
    long_answer = "당신의 일지 사(巳)는… " + "가" * 5000
    with patch.object(C, "_call_ollama", fake_call):
        C._correct_branches(long_answer, allowed={"day": {"亥"}}, truth="t",
                            question="q", sys_content="s", saju_summary=None,
                            initial_bad=[("일지", "巳", "亥")])
    assert captured["nps"] and captured["nps"][0] == 4096  # 장문 → 캡 4096


def test_sinnyeon_prompt_has_quality_guards():
    """신년운세 프롬프트에 표복사 금지·쉬운말·반복금지·분량상한·한글(한글)금지 지시 포함."""
    from backend.app.services.tool_service import SINNYEON_SYSTEM as S
    assert "복사" in S and "쉬운" in S and "반복" in S
    assert "3,500~4,500자" in S and "정재(정재)" in S  # 금지 예시 명시


def test_stored_reports_cleaned_on_read():
    """저장본 재열람 경로 4곳(tool·chat·compat·tarot) 전부 정리 체인 적용 — 수정 전 생성된
    리포트의 '---'·오병기·중복이 재열람마다 노출되던 실측(운영자 지적) 소급 방지."""
    import inspect
    from backend.app.services import compat_service as CP
    from backend.app.services import tarot_service as TR
    from backend.app.services import tool_service as TS
    assert "fix_term_hanja" in inspect.getsource(TS.get_tool)
    assert "fix_term_hanja" in inspect.getsource(C._row_to_messages)
    assert "fix_term_hanja" in inspect.getsource(CP.get_compatibility)
    assert "fix_term_hanja" in inspect.getsource(TR.get_tarot)
    # 운영자 실물(저장본) 그대로 — 재열람 정리 결과
    t = "직업운 점수: 70\n내용입니다.\n\n---\n\n재물 운\n내용2입니다."
    out = fix_term_hanja(t)
    assert "---" not in out and "\n\n\n" not in out and "재물 운" in out


def test_paid_menu_richness_guards():
    """유료 메뉴 분량 백스톱·구조 강제(운영자 지시: 돈 받는 메뉴가 빈약하면 안 됨)."""
    import inspect
    from backend.app.services import tool_service as TS
    from backend.app.services import compat_service as CP
    src = inspect.getsource(_tool_stream_body(TS))
    assert "분량 백스톱" in src and '"sinnyeon": 3000' in src and '"taekil": 1300' in src \
        and '"naming": 1300' in src
    assert "절대 추가하지 마세요" in src            # 확장 재생성에도 환각 금지 명시
    # [2026-07-25] compat 도 본문이 _stream_message_inner 로 분리됨 — tool 과 동일하게 헬퍼로 본문을 본다
    # (종전엔 얇은 환불 래퍼 stream_message 만 검사해 본문 가드를 못 봄 → 선재 실패였음).
    src2 = inspect.getsource(_tool_stream_body(CP))
    assert "분량 백스톱" in src2 and "1600" in src2  # 궁합(실측 889자) 백스톱
    # 구조 강제 프롬프트
    assert "각각 별도 문단" in TS.NAMING_SYSTEM and "1,500자" in TS.NAMING_SYSTEM
    assert "각각 별도 문단" in TS.TAEKIL_SYSTEM and "1,500자" in TS.TAEKIL_SYSTEM
    assert "각각 2문단씩" in TS.SINNYEON_SYSTEM
    assert "각각 별도 문단" in CP.COMPAT_SYSTEM and "1,800자" in CP.COMPAT_SYSTEM


def test_qwen_system_has_repeat_and_ending_guards():
    """qwen 보강 시스템에 반복·표복사 금지 + 완결 문장 끝맺음 지시 포함."""
    assert "반복" in C._QWEN_REFINE_SYSTEM and "복사" in C._QWEN_REFINE_SYSTEM
    assert "끝맺음" in C._QWEN_REFINE_SYSTEM


def test_safe_replace_gate():
    """[2026-07-22 교체 안전 게이트] 보강·교정본이 잘린 모양/과단축이면 교체 거부(원본 유지).

    실측: 초안은 12월까지 완결이었는데 보강이 만든 '**에너지가'에서 끊긴 본문이 교체됨."""
    full = ("완결된 월별 해설 문장입니다. " * 100).strip() + " 마무리 조언입니다."
    cut = full[:1500] + "내 일간 병(丙)과 월지 유(酉)가 충 관계를 맺어, **에너지가"
    assert C._looks_truncated(cut)
    assert C._safe_replace(full, cut) is None                      # 잘린 보강본 거부
    assert C._safe_replace(full, full + " 보강 완료입니다.")        # 정상 보강본 통과
    assert C._safe_replace(full, full[: len(full) // 2].rstrip() + "다.") is None  # 과단축 거부
    assert not C._looks_truncated("정상적으로 끝나는 문장입니다.")
    # qwen·Claude 보강, 교정 재생성, 분량 확장 전 경로 배선 확인
    import inspect
    from backend.app.services import compat_service as CP
    from backend.app.services import tool_service as TS
    assert "_safe_replace" in inspect.getsource(C._refine_with_qwen)
    assert "_safe_replace" in inspect.getsource(C._claude_boost)
    assert "_safe_replace" in inspect.getsource(C._deep_refine)
    assert "_safe_replace" in inspect.getsource(C._correct_branches)
    assert "_safe_replace" in inspect.getsource(_tool_stream_body(TS))
    assert "_safe_replace" in inspect.getsource(_tool_stream_body(CP))  # 본문(_stream_message_inner) 검사


def test_copied_table_lines_stripped():
    """[2026-07-22 실측] 월별 머리의 근거표 복사 불릿('- 월간 십성: …', '- 관계: …') 결정적 제거.

    서술이 남는 달만 제거하고, 표만 있는 달은 보존해 빈칸을 만들지 않는다."""
    with_body = ("#### 1월 (기축월)\n- 월간 십성: **상관(傷官)**, 월지 십성: **상관(傷官)**\n"
                 "- 관계: **무난**\n- **흐름**: 새로운 기회가 생길 수 있는 달입니다.\n"
                 "- **활용 조언**: 협력을 잘 활용하세요.")
    out = fix_term_hanja(with_body)
    assert "월간 십성" not in out and "- 관계:" not in out
    assert "흐름" in out and "활용 조언" in out
    only_table = ("#### 12월 (경자월)\n• 월간 십성: 편재(偏財), 월지 십성: 정관(正官)\n"
                  "• 관계: 월운 지지 자(子)↔내 월지(직장궁) 묘(卯) 형")
    assert "월간 십성" in fix_term_hanja(only_table)      # 서술 없는 달은 보존(빈칸 방지)
    keep = "- **흐름**: 좋은 달입니다.\n- 관계없이 편하게 지내세요."
    assert fix_term_hanja(keep) == keep                    # 일반 서술 무회귀


def test_sinnyeon_seun_relations_and_bigyeon_guard():
    """[2026-07-22 환각] '병화와 병화의 합' — 일간과 세운 천간이 같은 글자면 비견(합 아님).
    세운↔명식 관계를 결정적으로 주입하고, 같은 글자일 때 '합' 서술을 명시 금지한다."""
    from datetime import date, timedelta
    from types import SimpleNamespace
    from backend.app.saju.engine import build_chart
    from backend.app.saju.types import BirthInput, CalendarType, Gender
    from backend.app.services import tool_service as TS
    ch = next(c for c in (
        build_chart(BirthInput(birth_date=date(1986, 1, 1) + timedelta(days=i),
                               calendar=CalendarType.SOLAR, gender=Gender.MALE))
        for i in range(60)) if c.pillars.day.stem == "丙")
    row = SimpleNamespace(tool="sinnyeon", kind=None, input_json={},
                          chart_json=ch.model_dump(mode="json"),
                          result_json={"year": 2026,
                                       "seun": {"stem_ko": "병", "branch_ko": "오",
                                                "stem": "丙", "branch": "午"},
                                       "day_stem": "丙", "day_strength": ch.day_master_strength,
                                       "domains": [], "months": []})
    out = TS._render(row)
    # 라벨도 쉬운 말로 — '세운↔내 명식 관계' → '올해 기운과 내 사주의 관계'
    assert "올해 기운과 내 사주의 관계(결정적):" in out
    assert "비견(比肩)입니다 — '합'이 아닙니다" in out


def test_structure_loss_rejected():
    """[2026-07-22 실측] 보강본이 길이·끝맺음은 정상인데 뒷달(11·12월) 서술만 증발한 경우 교체 거부.

    화면 실측: 11·12월이 근거표 2줄만 남고 서술이 통째로 사라진 채 '마무리 조언'으로 끝남
    (길이 91%·끝맺음 정상이라 잘림/과단축 검사를 통과하던 사각지대)."""
    def mk(full):
        s = ["### 월별 흐름"]
        for m in range(1, 13):
            s += [f"#### {m}월 (월간지)",
                  "- 월간 십성: **상관(傷官)**, 월지 십성: **편관(偏官)**", "- 관계: **무난**"]
            if m in full:
                s += [f"- **흐름**: {m}월은 이러한 흐름입니다. 설명이 이어집니다.",
                      f"- **활용 조언**: {m}월엔 이렇게 하세요."]
        s += ["### 마무리 조언", "2026년은 좋은 해입니다. 잘 대비하세요."]
        return "\n".join(s)
    orig, gutted = mk(range(1, 13)), mk(range(1, 11))
    assert not C._looks_truncated(gutted) and len(gutted) > len(orig) * 0.75  # 기존 검사 통과형
    assert C._safe_replace(orig, gutted) is None            # 구조 증발 → 거부
    assert C._safe_replace(orig, orig + " 보강 문장.") is not None  # 정상 보강 무회귀
    counts = C._section_body_counts(orig)
    assert counts["12"] == 2 and all(v == 2 for v in counts.values())  # 헤딩 잔여 오카운트 없음


def test_false_hap_neutralized():
    """[2026-07-22 브라우저 실측] 거짓 '합(合)' 주장 결정적 중화.

    실측 환각: "병(丙)은 을(乙)와의 합"(乙丙은 합 아님 — 을경합·병신합),
    "병화(丙火)와 병화(丙火)의 합"(같은 글자는 비견). 합은 고정표라 명식 없이 판정 가능.
    """
    out1 = fix_term_hanja("특히, 병(丙)은 을(乙)와의 합으로 인해, 추진력이 살아납니다.")
    assert "합으로" not in out1 and "관계로" in out1
    out2 = fix_term_hanja("병화(丙火)와 병화(丙火)의 합이 생기면서 추진력이 강해집니다.")
    assert "의 합이" not in out2 and "관계가" in out2
    # 진짜 합·삼합·반합·무관 문장은 보존(무회귀)
    for keep in ("병(丙)과 신(辛)의 합으로 결실이 생깁니다.",
                 "자(子)와 축(丑)의 합이 이루어집니다.",
                 "인(寅)·오(午)·술(戌) 삼합이 이루어집니다.",
                 "해(亥)와 묘(卯)의 반합이 생깁니다.",
                 "월운 지지 자(子)↔내 월지 묘(卯) 형 관계입니다."):
        assert fix_term_hanja(keep) == keep, keep
    assert fix_term_hanja(out1) == out1        # 멱등


def test_truncation_detector_markdown_tail():
    """[2026-07-22 오탐] 마크다운 강조로 끝나는 정상 문장('…참고용이에요.**')을 잘림으로
    오판하면 정상 보강본이 폐기된다(꿈해몽 실측). 종결 판정은 꼬리 기호를 벗겨서,
    '**' 짝 검사는 원문으로 분리 수행."""
    assert not C._looks_truncated("**꿈풀이는 전통 문화 콘텐츠로, 참고용이에요.**")
    assert not C._looks_truncated("**직업**은 좋고 **재물**은 조심하세요.")
    assert C._looks_truncated("…맺어, **에너지가")      # 열린 굵게 = 진짜 잘림
    assert C._looks_truncated("이는 새로운 환경이나")     # 평문 잘림


def test_month_section_splice():
    """[2026-07-22 실측] 4월은 충실한데 5·6·7월은 근거표 2줄만 — 한 번에 4천자 생성 시 뒷달 열화.
    월별만 따로 생성해 그 구간을 통째로 교체하되, 총운·영역별·마무리는 보존한다."""
    orig = ("### 총운\n2026년은 좋은 해입니다. 충분한 총운 서술입니다.\n\n"
            "### 직업/일\n직업운 점수 70점. 충분한 영역 서술입니다.\n\n"
            "### 월별 흐름\n"
            "#### 4월 (임진월)\n- 월간 십성: 편관, 월지 십성: 식신\n- 관계: 충\n"
            "- **흐름**: 직장에서 부담이 생길 수 있는 달입니다.\n- **활용 조언**: 휴식이 중요합니다.\n"
            "#### 5월 (계사월)\n- 월간 십성: 정관, 월지 십성: 비견\n- 관계: 해\n"
            "#### 6월 (갑오월)\n- 월간 십성: 편인, 월지 십성: 겁재\n- 관계: 반합\n\n"
            "### 마무리 조언\n2026년은 잘 대비하면 좋은 해입니다.")
    mon = "\n".join(
        f"#### {m}월 (간지월)\n"
        f"- **흐름**: {m}월은 재물과 책임이 함께 움직이는 달로, 지난달 흐름이 이어지며 새 일이 들어옵니다.\n"
        f"- **생길 수 있는 일**: 직장에서 새 역할을 맡거나 지출이 늘어나는 일이 생길 가능성이 있어요.\n"
        f"- **조심할 일**: 사람 사이 오해로 말이 길어질 수 있으니 약속은 문서로 남겨 두세요.\n"
        f"- **활용 조언**: {m}월엔 급하게 정하기보다 한 박자 늦춰 확인하고 움직이면 좋겠습니다."
        for m in range(4, 10))
    out = C._splice_month_section(orig, mon)
    assert out and "### 총운" in out and "충분한 총운 서술" in out      # 총운 보존
    assert "직업운 점수 70점" in out                                    # 영역 보존
    assert "### 마무리 조언" in out and "잘 대비하면" in out            # 마무리 보존
    assert not C._thin_month_keys(out)                                  # 빈약한 달 해소
    # 개선이 없으면 교체하지 않는다(무회귀)
    assert C._splice_month_section(orig, mon.split("#### 7월")[0]) is None


def _month_block(n, lines):
    body = "\n".join(f"- {n}월 서술 {i} 실제 내용이 담긴 문장입니다." for i in range(lines))
    return f"#### {n}월 (간지월)\n- 월간 십성: 정재\n- 관계: 육합\n{body}\n"


def test_safe_replace_rejects_partial_month_thinning():
    """[2026-07-22 운영자 실측 '윗부분은 정상, 아래 부분은 봐봐'] 교정 재생성이 앞달은 그대로 두고
    뒷달만 한 줄로 얇게 만드는 부분 열화. 길이비가 0.75라서 min_ratio=0.6(교정 경로 실제값)을
    통과하고 '빈 달 0줄' 검사도 피해 갔다 → 서술 줄 총량·달별 얇아짐으로 별도 차단."""
    head = "## 총운\n" + ("올해는 흐름이 이러합니다. " * 40) + "\n\n## 월별 흐름\n"
    tail = "\n## 마무리 조언\n" + ("차분히 준비하시면 좋겠습니다. " * 20)
    orig = head + "".join(_month_block(n, 6) for n in range(1, 13)) + tail

    # 뒷달만 열화(1~6월 6줄 유지, 7~12월 1줄) — 길이비 0.75로 종전 게이트를 통과하던 케이스
    thinned = head + "".join(_month_block(n, 6 if n <= 6 else 1) for n in range(1, 13)) + tail
    assert len(thinned) > len(orig) * 0.7                 # 길이만으로는 못 잡는다(전제 고정)
    assert C._safe_replace(orig, thinned, min_ratio=0.6) is None

    # 전 달이 얇아지는 케이스도 거부
    allthin = head + "".join(_month_block(n, 1) for n in range(1, 13)) + tail
    assert C._safe_replace(orig, allthin, min_ratio=0.6) is None


def test_safe_replace_allows_genuine_correction():
    """무회귀: 구조·분량을 지키면서 틀린 간지만 고친 정상 교정본은 반드시 교체돼야 한다
    (게이트를 조이다 진짜 교정까지 막으면 환각이 그대로 남는다)."""
    head = "## 총운\n" + ("올해는 흐름이 이러합니다. " * 40) + "\n\n## 월별 흐름\n"
    tail = "\n## 마무리 조언\n" + ("차분히 준비하시면 좋겠습니다. " * 20)
    orig = head + "".join(_month_block(n, 6) for n in range(1, 13)) + tail
    fixed = orig.replace("정재", "편재")                   # 십성 교정만, 구조 동일
    assert C._safe_replace(orig, fixed, min_ratio=0.6) == fixed.strip()

    # 한 달만 6→2줄로 줄어든 정도(총량 유지)는 허용 — 과도한 거부 방지
    mild = head + "".join(_month_block(n, 2 if n == 3 else 6) for n in range(1, 13)) + tail
    assert C._safe_replace(orig, mild, min_ratio=0.6) is not None


def test_relation_self_paren_hanja():
    """[2026-07-22 라이브 실측] 신년운세 본문에 '형(형)' 4·'파(파)' 3·'합(합)' 3·'해(해)' 1 잔존.
    한 글자 관계어는 TERM_HANJA 밖이라 교정되지 않았다. 자기반복 병기만 정자로 바꾸고,
    정상 병기('올해(丙午)')·다른 뜻('형(兄)')·복합어('반합(半合)')는 건드리지 않는다."""
    from backend.app.saju.constants import fix_term_hanja as F
    assert F("형(형)") == "형(刑)"
    assert F("파(파)") == "파(破)"
    assert F("합(합)") == "합(合)"
    assert F("해(해)") == "해(害)"
    # 무손상 — 간지 병기·연도·복합 관계어·다른 뜻의 한자
    for keep in ("올해(丙午)", "올해(2026)", "반합(半合)", "삼형(三刑)", "형(兄)", "금년 해(害)"):
        assert F(keep) == keep, keep
    # 멱등
    once = F("월지 묘(卯)와 파(파), 년지 오(午)와 형(형)을 이룹니다.")
    assert F(once) == once and "파(破)" in once and "형(刑)" in once


def test_dedupe_never_deletes_bullet_lines_or_leaves_gaps():
    """[2026-07-22 전수감사 실측] 중복 제거가 줄 전체를 지워 ①본문 구멍 ②빈 줄을 남겼다
    (작명·아호: 이름마다 반복되는 '- **수리 4격**: …' 불릿이 통째로 삭제). 항목/제목 줄은
    각 이름·각 달의 고유 내용이므로 보존하고, 평문만 줄째로 없애며 공백은 접는다."""
    from backend.app.saju.constants import fix_term_hanja as F

    # ① 불릿 줄은 보존 — 삭제도 빈 줄도 없어야 한다
    t = ("- **수리 4격**: 원격 15획으로 좋습니다. 이는 아주 좋습니다.\n"
         "- **수리 4격**: 원격 15획으로 좋습니다.")
    o = F(t)
    assert o.count("수리 4격") == 2                      # 구멍 없음
    assert not any(line.strip() == "" for line in o.split("\n"))

    # ② 평문 완전중복은 계속 제거하되 빈 줄을 남기지 않는다
    dup = "이 달에는 감정적인 갈등이 생길 수 있습니다."
    o2 = F(f"첫 문단 내용입니다.\n\n{dup}\n\n끝 문단 내용입니다.\n\n{dup}")
    assert o2.count(dup) == 1
    assert "\n\n\n" not in o2

    # ③ 문단 내 반복 제거는 종전대로
    o3 = F("정재의 강한 기운은 재물을 뜻합니다. 정재의 강한 기운은 재물을 뜻합니다. 그러니 조심하세요.")
    assert o3.count("정재의 강한 기운은") == 1 and "그러니 조심하세요." in o3

    # ④ 원래 있던 큰 공백도 접힌다 + 멱등
    o4 = F("가나다 문단 하나입니다.\n\n\n\n\n라마바 문단 둘입니다.")
    assert "\n\n\n" not in o4
    for x in (o, o2, o3, o4):
        assert F(x) == x


def test_mixed_ganji_paren_kept_readable_not_overwritten():
    """[2026-07-22 라이브 실측] 택일 '황도(金궤)' 3회 — 엔진 값은 한글 '금궤'인데 모델이 한자를 섞었다.
    같이 드러난 기존 결함: 혼합 병기에는 간지 보호 가드가 없어 '일간(을木)'이 '일간(日干)'으로
    덮여 간지가 소실됐다. 명리 문맥어 뒤 깨진 병기는 용어 교정보다 먼저 한글 간지로 살린다."""
    from backend.app.saju.constants import fix_term_hanja as F
    assert F("황도(金궤)와 건제(성)") == "황도(금궤)와 건제(성)"
    assert F("일간(을木)이 강합니다.") == "일간(을목)이 강합니다."     # 종전: 일간(日干) — 간지 소실
    assert F("대운(丙오)에 들어섭니다.") == "대운(병오)에 들어섭니다."
    # 무손상 — 정상 한자 병기, 순한글 병기, 문맥어가 아닌 말(성씨 金=김 오교정 방지), 알려진 용어
    for keep in ("용신(庚金)이 필요합니다.", "일지(유)", "세운(丙午)", "일간(丙火)",
                 "이름(金수현)", "자원오행(한자부수)"):
        assert F(keep) == keep, keep
    assert F("원진(原진)이 있습니다.") == "원진(怨嗔)이 있습니다."      # 알려진 용어는 종전대로 정자


def test_false_hap_uses_nearest_two_ganji():
    """[2026-07-22 전수감사] 거짓 '합' 중화기가 24자 창 안에서 왼쪽 피연산자를 엉뚱한 병기로 물어
    ①庚·乙 천간합, 辰·酉 육합 같은 진짜 합까지 지우고(근거 소실) ②'관계의 관계' 비문을 남겼다.
    반대로 창을 좁히면 사이에 '목(木)'이 끼는 거짓 합을 놓친다 → 판정을 '직전 두 간지 병기'로 바꾼다."""
    from backend.app.saju.constants import _fix_false_hap as H

    # 진짜 합은 다른 병기가 앞에 나열돼도 보존
    for keep in ("월운 천간 경(庚)과 내 일간 을(乙)는 합의 관계를 맺습니다.",
                 "진(辰)과 유(酉)는 합의 관계를 맺습니다.",
                 "묘(卯)는 흔들리고, 경(庚)과 을(乙)는 합을 이룹니다.",
                 "해(亥)와 묘(卯)는 반합의 관계를 맺고",
                 "인(寅)·오(午)·술(戌) 삼합을 이룹니다.",
                 "종합적으로 보면 좋습니다."):
        assert H(keep) == keep, keep

    # 거짓 합은 사이에 다른 병기가 끼어도 중화되고, '관계의 관계' 비문이 생기지 않는다
    o = H("일간은 을(乙)으로, 이는 목(木)의 기운을 지닌 것으로, 병(丙)과는 합의 관계를 맺습니다.")
    assert "합" not in o and "관계의 관계" not in o and "관계를 맺습니다" in o
    o2 = H("병화(丙火)와 병화(丙火)의 합을 이룹니다.")           # 같은 글자 = 비견
    assert "합" not in o2 and "관계를 이룹니다" in o2
    o3 = H("유(酉)는 흔들리고, 병(丙)과 을(乙)는 합을 이룹니다.")
    assert "합" not in o3

    for t in (o, o2, o3):
        assert H(t) == t                                        # 멱등


def test_thin_month_detection_by_chars_not_only_lines():
    """[2026-07-22 전수감사] 뒷달 열화가 백스톱을 빠져나가던 진짜 이유: _section_body_counts 는
    '줄 수'만 세는데 한 문단형으로 쓴 달은 내용이 3문장으로 쪼그라들어도 1줄이라 v==0 조건이
    절대 성립하지 않았다(실측 11월 121자·12월 101자인데 '빈 달 0건'). 글자 수로도 판정한다."""
    head = "### 월별 흐름\n"
    full = "이 달은 흐름이 이렇고 생길 수 있는 일과 조심할 일, 활용 조언까지 충분히 담은 서술입니다. " * 3
    thin = "이 달은 관계만 나열되고 끝납니다."
    text = head + "".join(f"#### {m}월 (간지월)\n{full if m <= 10 else thin}\n" for m in range(1, 13))

    scan = C._section_body_scan(text)
    assert scan["1"][1] > 140 and scan["11"][1] < 140
    assert [k for k, v in C._section_body_counts(text).items() if v == 0] == []   # 종전 판정은 통과시킴
    assert C._thin_month_keys(text) == ["11", "12"]                               # 신규 판정은 잡아냄

    # 정상 출력(실측 208~300자/달)은 오탐하지 않는다
    ok = head + "".join(f"#### {m}월 (간지월)\n{full}\n" for m in range(1, 13))
    assert C._thin_month_keys(ok) == []


def test_false_hap_never_breaks_korean_verbs():
    """[2026-07-22 2라운드 감사 — 내가 만든 회귀] 판정 로직을 바꾸며 매칭 정규식을 맨 '합'으로
    바꾼 탓에 낱말 속 '합'까지 치환해 '형성합니다'→'형성관계니다'(실제 답변에 5회 노출),
    '결합합니다'→'결관계관계니다', '종합하면'→'종관계하면' 이 됐다.
    관계어 '합'은 앞뒤가 한글이 아닌, 홀로 선 낱말일 때만 잡는다."""
    from backend.app.saju.constants import _fix_false_hap as H

    # 한국어 낱말 속 '합'은 절대 건드리지 않는다(간지 병기가 앞에 있어도)
    for keep in ("월운 지지 신(申)은 월지(卯)와 원진을 이루며, 일지(亥)와 해(亥)를 형성합니다.",
                 "시지(未)와 형을 이루는 복잡한 관계를 형성합니다.",
                 "월지(卯)와 일지(亥)의 기운이 결합합니다.",
                 "월지 묘(卯)와 세운 오(午)를 종합하면 좋습니다.",
                 "일지(亥)와 월지(卯)는 서로 반합을 합니다.",
                 "경(庚)과 을(乙)는 육합입니다."):
        assert H(keep) == keep, keep
    # '합이다'는 종결형 커버 확장(4라운드) 이후 올바르게 중화된다 — 丙丙은 비견이지 합이 아니다.
    assert H("병(丙)과 병(丙)의 합이다.") == "병(丙)과 병(丙)의 관계이다."

    # 중화 기능 자체는 그대로
    assert "합" not in H("일간은 을(乙)으로, 목(木)의 기운이라 병(丙)과는 합의 관계를 맺습니다.")
    assert "합" not in H("병화(丙火)와 병화(丙火)의 합을 이룹니다.")
    for real in ("월운 천간 경(庚)과 내 일간 을(乙)는 합의 관계를 맺습니다.",
                 "진(辰)과 유(酉)는 합의 관계를 맺습니다."):
        assert H(real) == real, real


def test_stored_hap_corruption_self_heals_on_read():
    """이미 저장된 답변에 남은 파괴 흔적('형성관계니다'·'종관계')은 재열람 시 스스로 복구된다.
    생성·읽기 공통 체인이므로 DB 마이그레이션 없이 소급 정리된다."""
    assert fix_term_hanja("일지(亥)와 해(亥)를 형성관계니다.") == "일지(亥)와 해(亥)를 형성합니다."
    assert fix_term_hanja("기운이 결관계관계니다.") == "기운이 결합합니다."
    assert fix_term_hanja("묘(卯)와 오(午)를 종관계하면 좋습니다.") == "묘(卯)와 오(午)를 종합하면 좋습니다."
    # '관계가다' → '합이다'로 되돌린 뒤 개선된 판정이 다시 본다: 丙丙은 비견이므로 '관계이다'가 정답
    assert fix_term_hanja("병(丙)과 병(丙)의 관계가다.") == "병(丙)과 병(丙)의 관계이다."
    # 정상적인 '관계' 문장은 절대 건드리지 않는다
    for keep in ("두 사람의 관계는 좋습니다.", "좋은 관계가 됩니다.", "관계의 흐름이 좋아요."):
        assert fix_term_hanja(keep) == keep, keep


def test_repeated_struct_line_keeps_value_drops_long_explanation():
    """[2026-07-22 2라운드 감사 — 내 A 수정의 부작용] 항목 줄을 통째로 보존하니 구멍은 사라졌지만
    같은 줄이 3회 그대로 노출됐다(아호 4런 4건). 이름 3개가 같은 결과인 건 사실이므로 값은 남기되
    되풀이되는 긴 설명만 덜어낸다 — 구멍도 없고 중복 읽힘도 없다."""
    line = ("- **수리 4격**: 길·길·길·길 — 모든 수리 조건이 완벽하게 충족되어, "
            "운세와 인연 모두에 길을 열어 줍니다.")
    t = "\n\n".join(f"### 추천 {i}: 이름{i}\n{line}" for i in (1, 2, 3))
    out = fix_term_hanja(t)
    assert out.count("수리 4격") == 3                 # 어느 이름도 구멍이 나지 않는다
    assert out.count("완벽하게 충족되어") == 1        # 긴 설명은 한 번만
    assert out.count("길·길·길·길") == 3              # 값 자체는 이름마다 남는다
    assert "\n\n\n" not in out
    assert fix_term_hanja(out) == out                  # 멱등

    # 값이 다르면 중복이 아니므로 원문 그대로
    diff = ("- **수리 4격**: 길·길·길·길 — 좋습니다.\n"
            "- **수리 4격**: 흉·길·길·길 — 보통입니다.")
    assert fix_term_hanja(diff) == diff


def test_repeated_struct_line_handles_korean_connective_form():
    """[2026-07-22] 실측 아호는 줄표가 아니라 '길·길·길·길로,' 처럼 연결 조사로 값과 설명을 잇는다.
    이 형태에서도 값만 남기고 설명을 덜어내야 중복이 사라진다(4개 런 전부 재현된 형식)."""
    a = "- **수리 4격**: 길·길·길·길로, **모든 측면에서 길한 기운**이 흐르는 아호입니다."
    b = "- **자원오행**: **금·수**로, 사주의 부족오행을 정확히 채워 줍니다."
    c = "**수리 4격**: [길·길·길·길]로, 수 기운을 강화하면서도 길을 걷는 데 유리한 이름입니다."
    for line, value in ((a, "길·길·길·길"), (b, "**금·수**"), (c, "[길·길·길·길]")):
        t = "\n\n".join(f"### 추천 {i}\n{line}" for i in (1, 2, 3))
        out = fix_term_hanja(t)
        assert out.count(value) == 3                       # 이름마다 값은 남는다(구멍 없음)
        assert out.count(line.split(value)[-1].strip()[:12]) == 1   # 설명은 한 번만
        assert fix_term_hanja(out) == out


def test_runaway_repetition_collapsed():
    """[2026-07-22 실측] 브리핑이 커져 컨텍스트를 먹자 모델이 같은 구절을 마침표 없이
    끝없이 되풀이하다 잘렸다('인연에 대한 기회가 생길 때까지는' × 수십 회).
    문장 단위 중복 제거는 종결부호가 없어 못 잡으므로 '같은 구절 3회 이상 연속'을 접는다."""
    bad = "앞 문장입니다. " + "인연에 대한 기회가 생길 때까지는 " * 10
    out = fix_term_hanja(bad)
    assert out.count("인연에 대한 기회") == 1
    assert out.startswith("앞 문장입니다.")
    # 정상 문장·목록·연속 숫자는 건드리지 않는다
    for keep in ("가나다 라마바 사아자.", "좋은 관계가 됩니다. 좋은 흐름이 이어집니다.",
                 "- 항목 하나", "2026년 2월 3월 4월 흐름"):
        assert fix_term_hanja(keep) == keep, keep
    assert fix_term_hanja(out) == out
