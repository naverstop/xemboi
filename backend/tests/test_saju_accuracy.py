"""사주 엔진 정확성 검증 스위트 — '한치의 오차 없음 + 근거 제시'를 코드로 보증.

원칙:
  - 추측값 금지. 각 단언은 **권위 출처 또는 도출 가능한 규칙**에만 근거한다.
  - 출처를 주석으로 명시한다. 누가 검증하러 와도 "이 값은 이 근거에서 나온다"를 즉시 제시.
  - 코드 변경으로 값이 틀어지면(회귀) 즉시 실패해 차단한다.

출처 약어:
  [IANA]   IANA tz database, zoneinfo "Asia/Seoul" (서머타임·역사 표준시 인코딩)
  [표준시]  위키백과 '한국 표준시' (표준자오선 변경: 127.5°/135°E)
  [건제]   건제십이신 구결 "建滿平收黑, 除危定執黃, 成開可用, 閉破不可當"
  [야자시] namestory.kr — 야자시: 일주=당일, 시주 천간=익일 일간 기준
  [칠요]   위키백과 '이십팔수' 역주(칠요 배당표)
  [EoT]    균시차 NOAA 약식 (진태양시 = 평균태양시 + 균시차)
"""
from __future__ import annotations

from datetime import date, time

from backend.app.saju.engine import build_chart
from backend.app.saju.pillars import (
    _adjust_time,
    _civil_std_offset_h,
    _equation_of_time_min,
    _kst_utcoffset_h,
)
from backend.app.saju.taekil import _GEONJE_INFO, _GEONJE_ORDER, _geonje
from backend.app.saju.types import BirthInput


def _adj(y, m, d, hh, mm, tst=False, lon=None, eot=False):
    b = BirthInput(birth_date=date(y, m, d), birth_time=time(hh, mm),
                   apply_true_solar_time=tst, birth_longitude=lon, apply_equation_of_time=eot)
    # _adjust_time → (표준일, 표준시각, 진태양시각). 시간 보정 결과 = 진태양시각(off면 표준시각과 동일).
    _, _std_t, solar_t = _adjust_time(b, date(y, m, d))
    return solar_t


# ============================================================
# 1) 진태양시 — (출생지 경도 − 그 시기 표준자오선) × 4분  [IANA][표준시]
# ============================================================
def test_true_solar_seoul_current_era():
    # 2000년(135°E): 서울 126.98° → (126.98-135)*4 = -32.08 ≈ -32분
    assert _adj(2000, 7, 15, 12, 0, tst=True, lon=126.98) == time(11, 28)

def test_true_solar_no_correction_when_off():
    # 진태양시 미적용 + DST/표준시 변경 없는 시기 → 시계 그대로
    assert _adj(2000, 7, 15, 12, 0, tst=False, lon=126.98) == time(12, 0)

def test_true_solar_city_longitude_differs():
    # 같은 시각도 출생지 경도에 따라 보정량이 달라야 한다 [표준시]
    assert _adj(2000, 7, 15, 12, 0, tst=True, lon=129.08) == time(11, 36)  # 부산 -24분
    assert _adj(2000, 7, 15, 12, 0, tst=True, lon=126.39) == time(11, 26)  # 목포 -34분


# ============================================================
# 2) 서머타임 자동 제거(항상) — 1948~51·55~60·87~88 출생  [IANA]
# ============================================================
def test_dst_1988_auto_removed():
    # 1988 서머타임(UTC+10) → 진태양시 미적용이라도 1시간 자동 제거
    assert _kst_utcoffset_h(date(1988, 7, 15), time(14, 0)) == 10.0   # [IANA]
    assert _adj(1988, 7, 15, 14, 0, tst=False) == time(13, 0)

def test_dst_1955_summer_127_5_era():
    # 1955 여름: 127.5°E 표준(+8.5) + 서머타임(+1) = +9.5 → 1시간 제거
    assert _kst_utcoffset_h(date(1955, 7, 15), time(12, 0)) == 9.5     # [IANA]
    assert _adj(1955, 7, 15, 12, 0, tst=False) == time(11, 0)

def test_no_dst_winter_127_5_unchanged_when_off():
    # 1960 겨울(127.5°E, 서머타임 없음): 진태양시 미적용 → 시계 그대로
    assert _adj(1960, 1, 15, 12, 0, tst=False) == time(12, 0)


# ============================================================
# 3) 역사적 표준자오선  [표준시]
# ============================================================
def test_historical_standard_meridian_offsets():
    assert _civil_std_offset_h(date(1910, 6, 1)) == 8.5    # 1908.4~1911: 127.5°E
    assert _civil_std_offset_h(date(1930, 6, 1)) == 9.0    # 1912~1954.3.20: 135°E
    assert _civil_std_offset_h(date(1958, 6, 1)) == 8.5    # 1954.3.21~1961.8.9: 127.5°E
    assert _civil_std_offset_h(date(1970, 6, 1)) == 9.0    # 1961.8.10~: 135°E


# ============================================================
# 4) 균시차 부호/범위 — 계절별 ±16분  [EoT]
# ============================================================
def test_equation_of_time_sign():
    feb = _equation_of_time_min(date(2000, 2, 11))   # 2월 중순: 음(약 -14분)
    nov = _equation_of_time_min(date(2000, 11, 3))   # 11월 초: 양(약 +16분)
    assert -16 < feb < -10
    assert 13 < nov < 17


# ============================================================
# 5) 건제십이신 — 월지==일지=建, 이후 順. 길흉 구결  [건제]
# ============================================================
def test_geonje_construction():
    # 2026-07-16은 未月·卯일 → (卯3 - 未7) mod 12 = 8 → order[8] = 成
    ch, score, _ = _geonje("未", "卯")
    assert ch == "成" and score >= 80
    # 월지==일지면 建(0)
    assert _geonje("子", "子")[0] == "建"
    assert _geonje("寅", "寅")[0] == "建"

def test_geonje_gilhyung_split():
    # 길: 除危定執成開 / 흉: 建滿平收閉破 (破·閉 大凶, 成·開·定 大吉)  [건제]
    gil = {"除", "危", "定", "執", "成", "開"}
    hyung = {"建", "滿", "平", "收", "閉", "破"}
    assert gil | hyung == set(_GEONJE_ORDER)            # 12신 전체 = 6길+6흉
    assert gil & hyung == set()                          # 겹치지 않음
    min_gil = min(_GEONJE_INFO[c][0] for c in gil)
    max_hyung = max(_GEONJE_INFO[c][0] for c in hyung)
    assert min_gil > max_hyung                           # 모든 길 > 모든 흉
    assert _GEONJE_INFO["破"][0] <= 28 and _GEONJE_INFO["閉"][0] <= 28  # 大凶
    assert _GEONJE_INFO["成"][0] >= 90                    # 大吉


# ============================================================
# 6) 자시(子時) 관법 — 23시 출생 일주/시주  [야자시]
# ============================================================
def _pillars(y, m, d, hh, mm, mode="yaja"):
    b = BirthInput(birth_date=date(y, m, d), birth_time=time(hh, mm), night_zi_mode=mode)
    return build_chart(b, with_daewoon=False).pillars

def test_night_zi_yaja():
    # 야자시: 일주=당일(戊午), 시주 천간=익일 일간(己) 기준 오자시법 → 甲子
    p = _pillars(2000, 1, 1, 23, 30, "yaja")
    assert p.day.stem + p.day.branch == "戊午"
    assert p.hour.stem + p.hour.branch == "甲子"

def test_night_zi_jeongja():
    # 정자시: 23시부터 일주·시주 모두 익일 → 일주 己未, 시주 甲子
    p = _pillars(2000, 1, 1, 23, 30, "jeongja")
    assert p.day.stem + p.day.branch == "己未"
    assert p.hour.stem + p.hour.branch == "甲子"

def test_non_zi_hours_mode_independent():
    # 자시 아닌 시각(22:30)은 두 관법이 동일해야 한다
    a = _pillars(2000, 1, 1, 22, 30, "yaja")
    b = _pillars(2000, 1, 1, 22, 30, "jeongja")
    assert (a.day.stem, a.hour.stem, a.hour.branch) == (b.day.stem, b.hour.stem, b.hour.branch)


# ============================================================
# 7) 이십팔수 칠요(요일) 잠금 불변식  [칠요]
#    표준 순서 인덱스 i → 요일 = (i+3) mod 7 (월=0..일=6) 가
#    위키백과 칠요 배당표와 완전히 일치해야 한다.
#    (28수 절대 위상 앵커는 신뢰 만세력 확정 전까지 미구현 — 여기선 칠요 잠금만 검증)
# ============================================================
_SU_SEQ = "角亢氐房心尾箕斗牛女虛危室壁奎婁胃昴畢觜參井鬼柳星張翼軫"
# 위키백과 '이십팔수' 역주 칠요 배당표 (월=0..일=6)
_CHILYO = {
    0: set("畢危心張"),   # 월요일
    1: set("翼觜室尾"),   # 화요일
    2: set("箕軫參壁"),   # 수요일
    3: set("奎斗角井"),   # 목요일
    4: set("鬼婁牛亢"),   # 금요일
    5: set("氐柳胃女"),   # 토요일
    6: set("虛房星昴"),   # 일요일
}

def test_28su_chilyo_lock():
    assert len(_SU_SEQ) == 28 and len(set(_SU_SEQ)) == 28
    for i, su in enumerate(_SU_SEQ):
        wk = (i + 3) % 7
        assert su in _CHILYO[wk], f"{su}(idx{i})는 요일 {wk}에 와야 하나 칠요표 불일치"
    # 칠요표는 각 요일당 정확히 4개 수
    for wk, sus in _CHILYO.items():
        assert len(sus) == 4


def _gz(p):
    return (p.year.stem + p.year.branch, p.month.stem + p.month.branch,
            p.day.stem + p.day.branch, p.hour.stem + p.hour.branch)

def test_saenggi_bokdeok_mechanism():
    # 변효 메커니즘 검증 — 조견표 앵커: 본명괘 兌(남2세) → 4/4 일치 [생기복덕 조견표]
    from backend.app.saju.sinsal import saenggi_bokdeok
    assert saenggi_bokdeok("兌", "戌")[0] == "생기"   # 戌亥=乾(상효변)
    assert saenggi_bokdeok("兌", "亥")[0] == "생기"
    assert saenggi_bokdeok("兌", "未")[0] == "복덕"   # 未申=坤
    assert saenggi_bokdeok("兌", "卯")[0] == "절명"   # 卯=震
    assert saenggi_bokdeok("兌", "子")[0] == "화해"   # 子=坎
    # 길흉 분류
    assert saenggi_bokdeok("兌", "戌")[1] == "길"
    assert saenggi_bokdeok("兌", "卯")[1] == "흉"
    # 귀혼 = 본명괘 자신
    assert saenggi_bokdeok("兌", "酉")[0] == "귀혼"


def test_birth_taekil_both_parents_and_hours():
    # 출산택일: 양부모 궁합 + 시각 추천 구조 검증
    from datetime import date as _d
    from backend.app.saju import taekil as tk
    from backend.app.saju.types import Gender
    p1 = build_chart(BirthInput(birth_date=_d(1990, 3, 15), birth_time=time(14, 30)))
    p2 = build_chart(BirthInput(birth_date=_d(1992, 8, 22), birth_time=time(14, 0), gender=Gender.FEMALE))
    res = tk.recommend_dates(p1, _d(2026, 7, 1), days=20, purpose="birth", top=5, user_chart2=p2)
    assert res.best, "추천 길일 있어야"
    top = res.best[0]
    assert top.best_hours and len(top.best_hours) >= 1   # 시각 추천 존재
    assert all("sijin" in h and "score" in h for h in top.best_hours)
    # 일반 용도는 시각추천 없음
    res2 = tk.recommend_dates(p1, _d(2026, 7, 1), days=20, purpose="wedding", top=3)
    assert not res2.best[0].best_hours


def test_bonmyeong_gwae_guseong():
    # 본명괘=구성 본명성(생년·성별) — 공개값 교차검증
    from backend.app.saju.sinsal import bonmyeong_gwae
    assert bonmyeong_gwae(1990, True) == "坎"    # 1990 남 = 一白水(坎)
    assert bonmyeong_gwae(2000, True) == "離"    # 2000 남 = 九紫火(離)
    assert bonmyeong_gwae(1990, False) == "艮"   # 1990 여 = 八白土(艮)
    assert bonmyeong_gwae(2000, False) == "乾"   # 2000 여 = 六白金(乾)


def test_saryeong():
    # 사령(월률분야) — 하늘도마뱀 앵커: 2026-06-09 午月 → 丙
    c = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48)))
    assert c.saryeong == "丙"
    # 寅月 여기(절입 직후)=戊 / 정기(후반)=甲
    assert build_chart(BirthInput(birth_date=date(2026, 2, 5))).saryeong == "戊"
    assert build_chart(BirthInput(birth_date=date(1972, 2, 28))).saryeong == "甲"
    # 분야일수표 무결성: 각 월 합계 28~31일 범위
    from backend.app.saju.sinsal import _BUNYA
    for mb, tbl in _BUNYA.items():
        assert 28 <= sum(n for _, n in tbl) <= 31, f"{mb} 분야일수 합 이상"


def test_napeum_table_matches_formula():
    # 납음 60갑자표 전사 정확성 — 대연수 공식과 전부 일치해야(전사 오류 자동 탐지)
    from backend.app.saju.sinsal import _NAPEUM, napeum_element_formula
    assert len(_NAPEUM) == 60
    for gz, (_nm, wx) in _NAPEUM.items():
        assert napeum_element_formula(gz[0], gz[1]) == wx, f"납음 불일치 {gz}"
    # 알려진 샘플
    from backend.app.saju.sinsal import napeum
    assert napeum("甲", "子") == ("해중금", "금")
    assert napeum("丙", "午") == ("천하수", "수")
    assert napeum("壬", "戌") == ("대해수", "수")


def test_twelve_life_sinsal_gongmang():
    # 십이운성·십이신살·공망 — 하늘도마뱀 만세력 샘플 교차검증
    # 2026-06-09 10:48 → 丙午년 甲午월 甲寅일 己巳시
    c = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48)),
                    with_daewoon=False)
    assert c.twelve_life == {"년": "사", "월": "사", "일": "건록", "시": "병"}
    assert c.twelve_sinsal == {"년": "장성", "월": "장성", "일": "지살", "시": "망신"}
    assert c.gongmang == ["子", "丑"]


def test_product_default_true_solar_on():
    # 제품 기본값: 진태양시 ON(전문 만세력 관행, '대한민국 -30분'). [BirthDTO]
    from backend.app.domain.chat_dto import BirthDTO
    dto = BirthDTO(birth_date=date(2000, 1, 1))
    assert dto.apply_true_solar_time is True


def test_chart_cross_check_manseryeok_2026():
    # 전문가 만세력(하늘도마뱀): 2026-06-09 10:48 양 →
    #   년 丙午 · 월 甲午 · 일 甲寅 · 시 己巳 (巳시)
    p = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48)),
                    with_daewoon=False).pillars
    assert _gz(p) == ("丙午", "甲午", "甲寅", "己巳")

def test_chart_cross_check_manseryeok_1972():
    # 전문가 만세력: 1972-02-28 06:00(卯시) 양, 여 →
    #   년 壬子 · 월 壬寅 · 일 己丑 · 시 丁卯  (입춘 1972-02-05 이후 → 壬子년 寅월)
    p = build_chart(BirthInput(birth_date=date(1972, 2, 28), birth_time=time(6, 0)),
                    with_daewoon=False).pillars
    assert _gz(p) == ("壬子", "壬寅", "己丑", "丁卯")


def test_28su_anchor_koyomi():
    # 앵커: 일본 코요미 2곳(koyominote·rekichu) 일치값 [koyomi]
    # 2026-06-08 危 / 06-09 室 / 06-10 壁 / 06-11 奎
    from backend.app.saju.taekil import _su28
    from datetime import date as _d
    assert _su28(_d(2026, 6, 8))[0] == "危"
    assert _su28(_d(2026, 6, 9))[0] == "室"
    assert _su28(_d(2026, 6, 10))[0] == "壁"
    assert _su28(_d(2026, 6, 11))[0] == "奎"


def test_28su_score_wedding_penalty():
    # 28수 길흉(歳事暦): 大吉宿 高 / 婚礼凶 수는 혼인·출산에서 강감점
    from backend.app.saju.taekil import _su28_score
    assert _su28_score("牛", "general") >= 88          # 大吉宿
    assert _su28_score("翼", "wedding") <= 35           # 婚礼凶 → 혼인 강감점
    assert _su28_score("翼", "general") > 35            # 일반 용도엔 감점 없음
    assert _su28_score("鬼", "general") >= 88           # 大吉宿
    assert _su28_score("鬼", "wedding") <= 35           # 단 혼인엔만 凶


def test_28su_engine_chilyo_self_consistency():
    # 엔진 계산이 칠요 잠금을 위반하지 않아야(앵커 시프트·계산오류 자동 탐지) [칠요]
    from backend.app.saju.taekil import _su28_index
    from datetime import date as _d, timedelta as _td
    base = _d(1950, 1, 1)
    for i in range(0, 30000, 13):   # ~80년치 샘플
        d = base + _td(days=i)
        idx = _su28_index(d)         # 내부 assert가 칠요 불일치 시 실패
        assert (idx + 3) % 7 == d.weekday()
