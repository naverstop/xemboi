"""최종 시점 재검증 게이트(_scrub_stale_year_ganji) 테스트.

내부+외부(Claude) 보강을 거친 최종 답변에서 과거연도·틀린 세운 간지를 결정적으로
중화하는지 검증한다(LLM 불필요 — 순수 함수). 보고된 환각 패턴을 직접 케이스화.
"""
from __future__ import annotations

import datetime as _dt

from backend.app.services import chat_service as cs

_CUR = cs._year_ko_hj(_dt.date.today().year)        # ('병오','丙午')
_NXT = cs._year_ko_hj(_dt.date.today().year + 1)    # ('정미','丁未')


# ===== 역방향(적대적): 어떤 형태든 환각이 새면 안 됨 =====

def test_adv_seun_keyword_wrong_ganji_corrected():
    # '올해 세운이 임오(壬午)로' — 세운 키워드 뒤 틀린 간지 → 실제 세운으로 교정
    out = cs._scrub_stale_year_ganji("올해 세운이 임오(壬午)로 활기찬 기운입니다.")
    assert "임오" not in out and "壬午" not in out
    assert f"{_CUR[0]}({_CUR[1]})" in out


def test_adv_next_year_seun_wrong_ganji_corrected():
    out = cs._scrub_stale_year_ganji("내년 세운은 임인(壬寅)이라 안정적입니다.")
    assert "임인" not in out and "壬寅" not in out
    assert f"{_NXT[0]}({_NXT[1]})" in out


def test_adv_hanja_mismatch_fixed_anywhere():
    # 한글-한자 불일치는 위치 무관 결정적 교정 (계묘=癸卯, 병오=丙午)
    assert "癸巳" not in cs._scrub_stale_year_ganji("계묘(癸巳)의 기운")
    assert "계묘(癸卯)" in cs._scrub_stale_year_ganji("계묘(癸卯)의 기운")  # 이미 맞으면 유지
    fixed = cs._scrub_stale_year_ganji("올해 세운 병오(丙申)는 강하다")  # 병오의 한자는 丙午
    assert "丙申" not in fixed


def test_adv_combined_all_forms():
    s = ("올해 세운이 임오(壬午)로 시작해, 내년 (임인, 壬寅)은 안정적이며, "
         "특히 2023년 계묘년(癸巳)에는 큰 변화가 옵니다.")
    out = cs._scrub_stale_year_ganji(s)
    for bad in ("임오", "壬午", "임인", "壬寅", "2023", "계묘", "癸巳", "癸卯"):
        assert bad not in out, f"잔존 환각: {bad} in {out!r}"
    assert f"{_CUR[0]}({_CUR[1]})" in out  # 올해 = 실제 세운


# ===== 전방향(정상): 올바른 값·일반 단어는 절대 손대지 않음 =====

def test_fwd_correct_current_seun_preserved():
    s = f"올해 세운이 {_CUR[0]}({_CUR[1]})로 화 기운이 강합니다."
    assert cs._scrub_stale_year_ganji(s) == s


def test_fwd_chart_pillar_hanja_preserved():
    # 명식 기둥(일주 병신=丙申 등) 올바른 한자는 보존
    s = "일주 병신(丙申), 년주 을묘(乙卯)로 구성됩니다."
    assert cs._scrub_stale_year_ganji(s) == s


def test_fwd_no_false_positive_on_gapjagi():
    # '갑자기'의 '갑자'가 간지지만 한자병기·세운앵커 없으니 손대면 안 됨
    s = "올해 세운이 갑자기 바뀌어 변화가 큽니다."
    assert cs._scrub_stale_year_ganji(s) == s
    s2 = "올해 갑자기 좋은 일이 생깁니다."
    assert cs._scrub_stale_year_ganji(s2) == s2


def test_fwd_non_ganji_hanja_preserved():
    # 갑목(甲木) 등 간지 아닌 한자병기는 보존
    s = "일간 갑목(甲木)의 기운이 강합니다."
    assert cs._scrub_stale_year_ganji(s) == s


def test_removes_past_year_and_wrong_ganji_with_hanja():
    out = cs._scrub_stale_year_ganji("특히 2023년 계묘년(癸巳)에는 인연이 자연스럽게 찾아옵니다.")
    assert "2023" not in out
    assert "계묘" not in out
    assert "癸巳" not in out


def test_removes_paren_wrong_ganji_keeps_normal_words():
    out = cs._scrub_stale_year_ganji("올해와 내년(계묘년)은 인연 형성에 유리한 시기로 보입니다.")
    assert "계묘" not in out
    assert "내년" in out          # 정상 시점어는 보존
    assert "(올해)" not in out     # 괄호 잔재 없음


def test_preserves_actual_current_year_ganji():
    allowed = cs._allowed_year_ganji()
    assert allowed, "올해/내년 세운 간지를 계산할 수 있어야 함"
    g = sorted(allowed)[0]
    out = cs._scrub_stale_year_ganji(f"올해 세운 {g}년에는 활기찬 기운이 함께합니다.")
    assert f"{g}년" in out         # 실제 세운 간지는 그대로 둠


def test_preserves_current_year_ganji_with_hanja_paren():
    # '병오(丙午)'처럼 년 없이 한자 병기된 현재 세운 표기는 손대지 않음
    out = cs._scrub_stale_year_ganji("올해 세운이 병오(丙午)로 화 기운이 강합니다.")
    assert "병오(丙午)" in out


def test_relative_year_paren_ganji_corrected():
    # '내년 (임인, 壬寅)' 처럼 간지 뒤 '년'이 없는 헤더 형태 — 실제 세운으로 강제 교정
    cur_ko, cur_hj = cs._year_ko_hj(__import__("datetime").date.today().year)
    nxt_ko, nxt_hj = cs._year_ko_hj(__import__("datetime").date.today().year + 1)
    out = cs._scrub_stale_year_ganji("올해 (임오, 壬午)는 활기차고, 내년 (임인, 壬寅)은 안정적입니다.")
    assert "임인" not in out and "壬寅" not in out
    assert "임오" not in out and "壬午" not in out
    assert f"올해 ({cur_ko}, {cur_hj})" in out   # 올해 = 실제 세운(병오 등)
    assert f"내년 ({nxt_ko}, {nxt_hj})" in out   # 내년 = 실제 세운(정미 등)


def test_relative_year_correct_ganji_preserved():
    cur_ko, cur_hj = cs._year_ko_hj(__import__("datetime").date.today().year)
    out = cs._scrub_stale_year_ganji(f"올해 ({cur_ko}, {cur_hj})는 화 기운이 강합니다.")
    assert f"올해 ({cur_ko}, {cur_hj})" in out   # 올바른 값은 그대로


def test_past_year_number_as_current_neutralized():
    # '올해는 2023년' 처럼 올해를 과거 연도 숫자로 단정 → 숫자 제거(올해로 중화), 깔끔하게
    out = cs._scrub_stale_year_ganji("올해는 2023년으로 변화가 큰 해입니다.")
    assert "2023" not in out
    assert "올해는 올해" not in out          # 잔재 중복 없음
    assert out.startswith("올해는")


def test_current_and_next_year_numbers_preserved():
    import datetime as _dt
    y = _dt.date.today().year
    out = cs._scrub_stale_year_ganji(f"올해 {y}년과 내년 {y+1}년은 기운이 다릅니다.")
    assert str(y) in out and str(y + 1) in out   # 올해·내년 숫자는 보존


def test_empty_safe():
    assert cs._scrub_stale_year_ganji("") == ""
    assert cs._scrub_stale_year_ganji(None) is None  # type: ignore[arg-type]
