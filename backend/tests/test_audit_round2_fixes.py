# -*- coding: utf-8 -*-
"""전수감사 2라운드(적대적 재검증)에서 확인된 결함 수정 (2026-07-22).

1차 감사 후 적대적 재검증이 잡아낸 것들:
  ① '파(상충)' 6건 — 破를 '상충'으로 옮겨 뜻까지 뒤집음. '형(形)'·'구설(구설)'도 미방어였다.
     (1차 진단 '파·형이 맵에 없다'는 오류였고, 실제로는 자기중복 형태만 교정했던 것)
  ② '庚(庚)'·'乙(乙)' 한자(한자) 병기 6건 — 규칙은 '항상 한글(한자)'.
  ③ 세운 십성이 brief 에 없어 창작 — 진실값 상관(傷官)·식신(食神)인데 '정재·정관'을 6회 주장.
  ④ 궁합 소제목 '십성(정재·정관)'은 채점 기준 라벨인데 커플의 십성처럼 인쇄돼 본문과 모순.
  ⑤ 종합 감정서 PDF만 정리 체인을 안 타 '---'·'劫財'가 그대로 인쇄.
  ⑥ 글꼴에 없는 글리프(⚠·✓·이모지)가 인쇄물에서 소리 없이 증발.
"""
import io
from datetime import date
from types import SimpleNamespace

from backend.app.saju.constants import fix_term_hanja as F
from backend.app.services import pdf_service as P

def _tool_stream_body(mod):
    """툴 스트림 '본문'을 돌려준다 — 공개 stream_message 는 과금 보상 래퍼라 본문 가드가 그 안에 없다.

    [2026-07-23] 스트림 예외 시 선차감 미환불을 고치면서 본문을 _stream_message_inner 로 옮겼다.
    래퍼가 없어지면 다시 stream_message 를 보므로, 구조가 바뀌어도 이 헬퍼만 유지되면 된다.
    """
    return getattr(mod, "_stream_message_inner", mod.stream_message)



def test_relation_paren_wrong_word_corrected():
    assert F("파(상충)을 이룹니다.") == "파(破)을 이룹니다."
    assert F("이는 형(形)을 이루며") == "이는 형(刑)을 이루며"
    assert F("구설(구설)이 있습니다") == "구설(口舌)이 있습니다"
    assert F("충(衝)이 있다") == "충(沖)이 있다"
    # 무손상 — 정상 병기·다른 뜻·간지 병기는 건드리지 않는다
    for keep in ("올해(丙午)", "그 해(2026)", "형(兄)", "일간(丙火)",
                 "삼합(三合)", "반합(半合)", "원진(怨嗔)", "정재(正財)", "형(亥亥)"):
        assert F(keep) == keep, keep
    once = F("파(상충)과 형(形)")
    assert F(once) == once                      # 멱등


def test_hanja_self_paren_becomes_korean_reading():
    assert F("辛(辛)과 乙(乙)는 충의 관계") == "신(辛)과 을(乙)는 충의 관계"
    assert F("庚(庚)") == "경(庚)"
    # 독음을 모르는 한자는 건드리지 않는다
    assert F("賢(賢)") == "賢(賢)"
    assert F(F("庚(庚)")) == F("庚(庚)")


def test_sinnyeon_brief_carries_seun_ten_god_and_relation_glossary():
    from backend.app.services.tool_service import _render
    from backend.app.saju.engine import build_chart
    from backend.app.saju.types import BirthInput
    cj = build_chart(BirthInput(birth_date=date(1990, 3, 21))).model_dump(mode="json")
    row = SimpleNamespace(
        tool="sinnyeon", kind="sinnyeon", input_json={}, chart_json=cj,
        result_json={"year": 2026, "day_stem": "乙", "day_strength": "neutral",
                     "seun": {"year": 2026, "stem": "丙", "branch": "午",
                              "stem_ko": "병", "branch_ko": "오"},
                     "domains": [{"label": "직업운", "value": 61}],
                     "months": []})
    brief = _render(row)
    # 일간 乙 기준 丙=상관, 午=식신 (엔진 결정값)
    assert "올해의 십성(결정적)" in brief      # 라벨도 쉬운 말로(운영자 "쉽게")
    assert "뜻: 학문·문서·후원" in brief or "뜻:" in brief   # 십성 뜻을 함께 줘 생활어로 풀게
    assert "상관(傷官)" in brief and "식신(食神)" in brief
    assert "그 밖의 십성을 올해 것이라 하지 마세요" in brief
    # 흉 관계를 길로 뒤집지 못하게 뜻을 못박는다
    assert "해(害)=서로 손해 보는 어긋남(흉)" in brief
    assert "좋은 기회로 뒤집어 쓰지 마세요" in brief
    # 내부 표 칸 이름을 문장에 옮기지 말라는 지시
    assert "내부 표의 칸 이름" in brief


def test_compat_factor_label_not_mistakable_for_actual_ten_god():
    from backend.app.services.compat_service import _FACTOR_LABEL
    assert "정재" not in _FACTOR_LABEL["ten_god"] and "정관" not in _FACTOR_LABEL["ten_god"]
    assert "십성" in _FACTOR_LABEL["ten_god"]


def test_pdf_renderer_cleans_defensively():
    """어느 경로가 정리 체인을 빠뜨려도 인쇄물은 깨끗해야 한다(종합 감정서 실측 사고)."""
    reader = __import__("pypdf")
    body = "---\n\n정재(정재)와 충(衝)은 원진(原진)입니다. 劫財 도 있습니다.\n\n본문 끝입니다."
    pdf = P.generate_consultation_pdf(doc_title="심층방어", person_line="테 스 트 님",
                                      item="항목" * 45, content=body, when=None)
    x = "".join((p.extract_text() or "") for p in reader.PdfReader(io.BytesIO(pdf)).pages)
    n = x.replace(" ", "")
    assert "정재(정재)" not in n and "정재(正財)" in n
    assert "충(衝)" not in n and "충(沖)" in n
    assert "원진(原진)" not in n and "원진(怨嗔)" in n
    assert "겁재(劫財)" in n
    assert "본문끝입니다" in n                 # 긴 항목명이 있어도 본문 손실 없음


def test_pdf_drops_unrenderable_glyphs_without_nul():
    reader = __import__("pypdf")
    body = "마커 ⚠ 체크 ✓ 선물 \U0001f381 별 ✦ 정상 ※★√"
    pdf = P.generate_consultation_pdf(doc_title="글리프", person_line="테 스 트 님",
                                      item="t", content=body, when=None)
    x = "".join((p.extract_text() or "") for p in reader.PdfReader(io.BytesIO(pdf)).pages)
    assert "\x00" not in x                      # .notdef 가 남지 않는다
    assert "※" in x and "√" in x      # ⚠→※, ✓→√ 치환 결과가 살아 있다
    assert "\U0001f381" not in x and "✦" not in x   # 그릴 수 없는 글자는 제거


def test_ganji_unit_paren_hanja():
    """[2026-07-22 상담 라이브 실측] '정미월(丁未월)'·'경술월(庚戌월)' — 괄호 안 단위만 한글로 남은
    혼합 병기. 괄호 앞뒤가 같은 간지를 가리키므로 단위를 정자로 맞춘다."""
    assert F("정미월(丁未월)으로") == "정미월(丁未月)으로"
    assert F("경술월(庚戌월)에") == "경술월(庚戌月)에"
    assert F("병오년(丙午년)은") == "병오년(丙午年)은"
    for keep in ("정미월(丁未月)", "내년(2027년)", "올해(丙午)", "7월(정미월)", "일간(을목)"):
        assert F(keep) == keep, keep
    assert F(F("정미월(丁未월)")) == F("정미월(丁未월)")


def test_chat_month_block_pins_relation_partner_position():
    """[2026-07-22 상담 라이브 실측] 브리핑은 '미(未)↔내 월지 묘(卯) 반합'인데 답변은
    '未와 일지 酉가 반합'으로 상대 자리를 바꿔치기했다(未·酉는 아무 관계도 아니다).
    종류뿐 아니라 '상대 자리'도 표 그대로 쓰라고 못박는다."""
    import inspect
    from backend.app.services import chat_service as CS
    src = inspect.getsource(CS._current_luck_block)
    assert "관계의 '종류'를 바꿔 부르지 마세요" in src
    assert "관계의 '상대 자리'도 표 그대로" in src
    assert "아무 관계도 아닌 짝을 근거로" in src


def test_false_hap_keeps_real_pair_in_enumeration():
    """[2026-07-22 3라운드] '직전 두 간지' 판정은 나열 문장에서 짝을 오인한다 —
    '유(酉)는 … 축(丑)과 반합, 진(辰)과 합'에서 {丑,辰}을 짝으로 보아 진짜 육합(酉辰)을 지웠다.
    근거를 지우는 해악이 거짓 합을 놓치는 것보다 크므로, 앞선 간지 중 **한 쌍이라도** 진짜 합이면 보존."""
    from backend.app.saju.constants import _fix_false_hap as H
    for keep in ("오늘 지지 유(酉)는 월지 축(丑)과 반합(半合), 일지 진(辰)과 합하는 관계로 만납니다.",
                 "년지 자(子)와 월지 축(丑), 일지 진(辰), 시지 사(巳)와 합이나 반합의 관계를 형성합니다.",
                 "일간 기(己)와 병(丙)은 특별한 합충 없이 조화롭게 상호작용합니다."):
        assert H(keep) == keep, keep
    # 거짓 합은 여전히 중화된다
    for t in ("일간은 을(乙)으로, 목(木)의 기운이라 병(丙)과는 합의 관계를 맺습니다.",
              "병화(丙火)와 병화(丙火)의 합을 이룹니다.",
              "유(酉)는 흔들리고, 병(丙)과 을(乙)는 합을 이룹니다."):
        assert "합" not in H(t), t


def test_stored_hap_artifacts_restored_then_rejudged():
    """저장본에 남은 '관계(合)'·'관계가나'·'관계충'을 원래 '합'으로 되돌린 뒤 개선된 판정으로 재평가."""
    from backend.app.saju.constants import _fix_false_hap as H
    assert H("일지 진(辰)과 관계(合), 시지 사(巳)와 반합하는 관계로") == \
        "일지 진(辰)과 합(合), 시지 사(巳)와 반합하는 관계로"
    assert H("특별한 관계충 없이") == "특별한 합충 없이"
    assert "합이나" in H("…와 관계가나 반합의 관계를")


def test_amulet_notation_terms():
    """부적 실측 오병기: '적(적)'(오방색)·'자형(자형)'."""
    assert F("적(적)") == "적(赤)"
    assert F("자형(자형)") == "자형(自刑)"
    for keep in ("적(赤)", "자형(自刑)", "붉은색(적색)"):
        assert F(keep) == keep, keep


def test_dream_session_persists_chart_json():
    """[2026-07-22 3라운드] 수정 J가 프로덕션에서 아예 발동하지 않았다 —
    persist_free_session 호출에 chart_json 이 없어 row.chart_json 이 None 이었다."""
    import inspect
    from backend.app.api import dream as D
    src = inspect.getsource(D)
    assert "saju_chart_json = ch.model_dump" in src
    assert "chart_json=saju_chart_json" in src


def test_tarot_generation_path_uses_cleanup_chain():
    """[2026-07-22 3라운드] 타로는 재열람에만 정리 체인이 걸려 있어 **첫 화면**에 '---'와
    중복 문장이 그대로 노출됐다. 생성 경로에도 적용(생성·읽기 대칭)."""
    import inspect
    from backend.app.services import tarot_service as T
    assert "fix_term_hanja" in inspect.getsource(_tool_stream_body(T))


def test_wuxing_overcome_direction_corrected():
    """[2026-07-22 3라운드] 궁합 오행 상극 역전은 근거를 2회 주입해도 3회 중 2회 재현됐다 —
    프롬프트로는 못 잡는다. 상극은 고정표(목극토·토극수·수극화·화극금·금극목)이므로 출력단에서 교정."""
    # ① 방향 역전 → 두 오행을 맞바꾼다(조사도 받침에 맞춰)
    assert F("금은 화를 극합니다.") == "화(火)는 금(金)을 극합니다."
    assert F("토는 목을 극합니다.") == "목(木)은 토(土)를 극합니다."
    assert F("금(金)이 화(火)를 억제하는 성질") == "화(火)가 금(金)을 억제하는 성질"

    # ② 참인 사실을 부정한 형태 → 긍정으로(그냥 지우면 '극습니다' 비문이 된다)
    assert F("화는 금을 극하지 않습니다.") == "화는 금을 극합니다."
    assert F("화는 금을 극하지 않아요.") == "화는 금을 극해요."
    assert F("화는 금을 극하지 않는다.") == "화는 금을 극한다."

    # 실측 원문: 한 문장에 ①②가 함께 있어 ①만 고치면 자기모순이 남는다
    out = F("명리학에서 **금은 화를 극(剋)**하고, **화는 금을 극하지 않습니다**.")
    assert "화(火)는 금(金)을 극(剋)" in out and "극하지 않" not in out

    # 무손상 — 옳은 방향, 상극이 아닌 관계, 틀린 방향의 부정(결과적으로 참)
    for keep in ("화는 금을 극합니다.", "목은 토를 극하고", "목은 화를 생합니다.",
                 "금은 화를 극하지 않습니다."):
        assert F(keep) == keep, keep
    # 상생도 방향이 있다(금생수) — '수는 금을 생한다'는 역방향이므로 교정 대상
    assert F("수는 금을 생합니다.") == "금(金)은 수(水)를 생합니다."
    assert F(F("금은 화를 극합니다.")) == F("금은 화를 극합니다.")


def test_false_hap_consumes_hanja_annotation():
    """중화할 때 '합(合)'의 한자 병기까지 같이 지운다 — 안 그러면 '관계(合)'라는
    정체불명 표기가 남는다(운영 DB 실측 잔존 1건). 진짜 합·삼합·반합 병기는 보존."""
    from backend.app.saju.constants import _fix_false_hap as H
    out = H("천간 병(丙)은 당신의 일간 을(乙)과 합(合)을 이루며")
    assert "관계를 이루며" in out and "(合)" not in out
    # 저장본에 남은 '관계(合)'도 복구 → 재판정 → 같은 결과
    assert H("천간 병(丙)은 당신의 일간 을(乙)과 관계(合)을 이루며") == out
    for keep in ("월운 천간 경(庚)과 내 일간 을(乙)는 합(合)을 이룹니다.",
                 "인(寅)·오(午)·술(戌) 삼합(三合)과 해(亥)·묘(卯) 반합(半合)"):
        assert H(keep) == keep, keep
    assert H(out) == out


def test_hanja_reading_paren_and_internal_labels():
    """[2026-07-22 4라운드] 프롬프트로 안 잡히던 3종을 출력단으로 옮겼다.

    ① 부적 '월지(月支)는 丑(구)' — 丑의 정독은 '축'인데 독음을 창작.
    ② 궁합 '금(金)은 토(土)를 생하며' — 상생도 방향이 있다(토생금).
    ③ 꿈해몽 '[내 사주]에 따르면…' — 리터럴을 프롬프트에서 뺀 뒤에도 3런 중 2런 유출.
    """
    assert F("월지(月支)는 丑(구)에요") == "월지(月支)는 丑(축)에요"
    assert F("금(金)은 토(土)를 생하며") == "토(土)는 금(金)을 생하며"
    assert F("[내 사주]에 따르면, 오행 중 목이 많아요.") == "오행 중 목이 많아요."
    assert F("[분석]에 의하면 좋습니다.") == "좋습니다."
    # 무손상 — 정독이 맞는 병기, 이름 한자, 옳은 상생, 일반 대괄호
    for keep in ("丙午(병오)년", "酉(유)와 만납니다", "賢(현)은 이름 한자",
                 "토(土)는 금(金)을 생하며", "목은 화를 생합니다", "대괄호[주의]는 유지"):
        assert F(keep) == keep, keep
    for t in ("丑(구)", "금(金)은 토(土)를 생하며", "[내 사주]에 따르면, 좋아요."):
        assert F(F(t)) == F(t)


def test_false_hap_counterexamples_from_hunter():
    """[2026-07-22 반례 사냥] 감사가 찾은 high 반례 4종.

    ① '갑술(甲戌)년의 술토는 묘(卯)와 합' — 괄호에서 첫 글자(甲)만 뽑아 진짜 육합(卯戌)을 지웠다.
       운영 DB 답변 735건 중 243건(33%)이 이런 2자 병기를 쓴다.
    ② '갑(甲)과 경(庚)은 합이 아닌 충 관계입니다' — 원문이 옳은데 '관계가 아닌'으로 망가뜨렸다.
       ('아닌'은 '아니'의 축약이라 가드 패턴에 따로 적어야 했다.)
    ③ '**합**을' → '**관계를' — 마크다운 강조를 먹어 굵게 표시가 깨졌다.
    ④ '우호적관계입니다' → '우호적합입니다' — 저장본 복구 규칙이 정상 표현을 파괴했다.
    """
    from backend.app.saju.constants import _fix_false_hap as H

    # ① 2자 병기 안의 지지까지 후보로 — 진짜 육합 보존
    for keep in ("갑술(甲戌)년의 술토는 묘(卯)와 합을 이룹니다.",
                 "병자(丙子)일주는 축(丑)과 합을 이룹니다.",
                 "임신(壬申)년의 신금은 사(巳)와 합을 이룹니다."):
        assert H(keep) == keep, keep

    # ② 참인 부정 서술은 불개입
    for keep in ("갑(甲)과 경(庚)은 합이 아닌 충 관계입니다.",
                 "정(丁)과 계(癸)는 합이 아니라 충입니다.",
                 "병(丙)과 무(戊)는 합을 이루지 않습니다.",
                 "병(丙)과 무(戊)는 합이 아닙니다."):
        assert H(keep) == keep, keep

    # ③ 마크다운은 되돌려 놓고, 조사·종결형은 제대로 교정
    assert H("**병(丙)**과 **무(戊)**는 **합**을 이룹니다.") == "**병(丙)**과 **무(戊)**는 **관계**를 이룹니다."
    assert H("**병(丙)**과 **무(戊)**는 **합**이 됩니다.") == "**병(丙)**과 **무(戊)**는 **관계**가 됩니다."
    assert H("병(丙)과 무(戊)는 합입니다.") == "병(丙)과 무(戊)는 관계입니다."
    assert H("**경(庚)**과 **을(乙)**는 **합**을 이룹니다.") == "**경(庚)**과 **을(乙)**는 **합**을 이룹니다."

    # ④ 정상 한국어 표현 무손상
    from backend.app.saju.constants import fix_term_hanja as FF
    for keep in ("두 사람은 우호적관계입니다.", "상호보완적관계를 이룹니다."):
        assert FF(keep) == keep, keep


def test_dedupe_month_context_vs_name_context():
    """[2026-07-22 반례 사냥 high] 같은 '항목 줄 완전중복'이라도 문맥에 따라 뜻이 반대다.
    월별 섹션의 달 간 복붙(운영 DB 12건 실측)은 지워야 하고, 작명·아호의 이름별 값은 지우면
    그 이름에 구멍이 난다. 달 소제목으로 문맥을 판정해 갈라 처리한다."""
    line = "- **건강:** 신체적 활동을 적절히 조절하고, 스트레스 관리에 신경 써야 합니다."
    month = f"### 월별 흐름\n#### 7월 (을미월)\n{line}\n#### 9월 (정유월)\n{line}"
    assert F(month).count("신체적 활동") == 1               # 달 간 복붙 → 제거

    nl = "- **수리 4격**: 길·길·길·길로, 모든 측면에서 길한 기운이 흐릅니다."
    names = "\n".join(f"### 추천 {i}: 이름{i}\n{nl}" for i in (1, 2, 3))
    out = F(names)
    assert out.count("수리 4격") == 3 and out.count("길·길·길·길") == 3   # 이름별 값 보존
    assert out.count("모든 측면에서") == 1                   # 긴 설명만 한 번


def test_dedupe_does_not_truncate_enumerated_values_or_tables():
    """[반례 사냥 medium] ①값이 쉼표로 나열되면 '로,'를 설명 시작점으로 오인해 값이 잘렸다
    (정격 33 증발). ②파이프 표 줄이 구조 줄로 인식되지 않아 두 번째 표의 헤더가 통째 삭제됐다."""
    v = "- **수리 4격**: 원격 25 길, 형격 12 흉, 이격 21 길로, 정격 33 길입니다."
    assert F(f"{v}\n{v}").count("정격 33") == 2               # 값 손실 없음

    tbl = "| 구분 | 내용 |\n| --- | --- |"
    out = F(f"### A\n{tbl}\n| 3월 | 재물운 |\n\n### B\n{tbl}\n| 4월 | 직업운 |")
    assert out.count("| 구분 | 내용 |") == 2                 # 두 번째 표가 살아 있다


def test_branch_verifier_catches_comparison_phrasing():
    """[반례 사냥 medium] '일지는 오늘 일진과 같은 오화(午)로' — 스코프 가드가 이런 비교 화법까지
    통과시켜 진짜 명식 오류를 놓쳤다(오늘운세의 지배적 화법). 비교 표현이 있으면 가드를 풀고,
    지지가 12자 창 밖으로 밀리므로 그때만 창을 넓힌다."""
    from backend.app.services.chat_service import _verify_branches as V
    allow = {"month": {"卯"}, "day": {"巳"}, "year": {"午"}}
    for t in ("오늘은 병오(丙午)일입니다. 일지는 오늘 일진과 같은 오화(午)로, 활동력이 올라갑니다.",
              "내 월지는 세운과 달리 오(午)입니다.",
              "당신의 월지는 세운과 마찬가지로 오화(午)의 자리라",
              "당신의 일지는 월운과 달리 축토(丑)라서 충의 압력이 커집니다."):
        assert V(t, allow), t                                 # 검출되어야 한다
    # 기존 오탐은 계속 통과(무회귀)
    for t in ("특히, 내 월지와 세운 지지 오(午)가 파를 맺고 있어요.",
              "내 월지와 대운 지지 신(申)이 충합니다.",
              "내 일지와 오늘 일진 자(子)가 만납니다.",
              "내 월지 묘(卯)는 목 기운입니다."):
        assert V(t, allow) == [], t


def test_month_heading_recognizes_real_formats_only():
    """[반례 사냥 high] 운영 DB 실제 헤딩('#### 1월: 기축월(己丑月) …', '- **1월 기축월 (己丑月)**')을
    종전 패턴이 전혀 못 잡아 월별 백스톱이 통째로 무발동했다. 반대로 접두를 안 요구하면 총운 안의
    '3월 전후로 …' 평문을 헤딩으로 오인해 그 위를 통째로 지운다 — 둘 다 막는다."""
    from backend.app.services.chat_service import _MONTH_HEAD_RE as R
    for head in ("#### 3월 (임진월)", "#### 1월: 기축월(己丑月) 월간 십성",
                 "- **1월 기축월 (己丑月)**", "**7월은 을미월입니다**", "## 12월", "* **5월** 흐름"):
        m = R.match(head)
        assert m and (m.group(1) or m.group(2)), head
    for body in ("3월 무렵 흐름이 바뀝니다.", "12월 20일(토)은 황도일이며",
                 "3월 전후로 큰 결정을 하게 되는데", "- 3월에는 재물운이 좋습니다",
                 "- 1월 서술 0 실제 내용이 담긴 문장입니다."):
        assert R.match(body) is None, body


def test_naming_hanja_leaves_common_words_alone():
    """[반례 사냥 high] 후보표에 '秀浩(수호)'가 있으면 본문의 '수호(守護)'를 '수호(秀浩)'로 바꿔
    문장을 무의미하게 만들었다('아이를 수호(秀浩)하는 기운'). 후보 이름 글자가 하나도 없는
    한자어는 이름이 아니다."""
    from backend.app.services.tool_service import fix_naming_hanja as X
    rj = {"candidates": [{"given": "秀浩", "reading": "수호"},
                         {"given": "祐周", "reading": "우주"},
                         {"given": "準雨", "reading": "준우"}]}
    for keep in ("이 이름은 아이를 수호(守護)하는 기운을 담고 있습니다.",
                 "아이는 하나의 소우주(小宇宙)입니다.",
                 "회사의 지원(支援)을 받습니다."):
        assert X(keep, rj) == keep, keep
    # 진짜 이름 오기는 계속 교정
    assert X("추천 2: 准雨(준우)", rj) == "추천 2: 準雨(준우)"


def test_naming_verifier_accepts_compound_surname():
    """[반례 사냥 medium] 복성 '남궁지호(南宮芝浩)'를 '완전 창작'으로 오판해 재생성을 헛돌렸다."""
    from backend.app.services.tool_service import _verify_naming_candidates as V
    rj = {"candidates": [{"given": "芝浩", "reading": "지호"}]}
    assert V("南宮芝浩(지호)를 추천합니다.", rj) == []      # 복성 + 후보 이름 → 정상
    assert V("金芝浩(지호)를 추천합니다.", rj) == []        # 단성 + 후보 이름 → 정상
    assert V("南宮智浩(지호)를 추천합니다.", rj)            # 표 밖 글자 → 검출
