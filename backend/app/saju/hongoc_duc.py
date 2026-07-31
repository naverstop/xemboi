"""베트남 음력(Âm lịch) 변환 — 호응옥득(Hồ Ngọc Đức) 알고리즘 이식.

베트남 공식 음력은 표준시 UTC+7 기준으로 계산되어, 중국 음력(sxtwl, UTC+8)과
경계일에서 하루~한 달(윤달 위치) 차이가 난다(예: 2007 뗏 = 2월 17일 vs 중국 춘절 2월 18일).
따라서 베트남 로케일은 sxtwl 대신 이 모듈로 음력↔양력을 변환한다.

알고리즘 출처: Hồ Ngọc Đức, "Âm lịch Việt Nam" (Jean Meeus 천문 알고리즘 기반).
timezone 파라미터로 기준 표준시를 받는다 — 베트남=7.0, 중국=8.0(검증용).
순수 함수(외부 의존 0). jdFromDate/jdToDate 는 그레고리력/율리우스력 경계(1582-10-15)를 처리한다.
"""
from __future__ import annotations

import math

_PI = math.pi


def jd_from_date(dd: int, mm: int, yy: int) -> int:
    """양력(dd/mm/yy) → 율리우스 적일(정수). 1582-10-15 이전은 율리우스력."""
    a = (14 - mm) // 12
    y = yy + 4800 - a
    m = mm + 12 * a - 3
    jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    if jd < 2299161:
        jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    return jd


def jd_to_date(jd: int) -> tuple[int, int, int]:
    """율리우스 적일(정수) → 양력 (dd, mm, yy)."""
    if jd > 2299160:  # 1582-10-15 이후 = 그레고리력
        a = jd + 32044
        b = (4 * a + 3) // 146097
        c = a - (b * 146097) // 4
    else:
        b = 0
        c = jd + 32082
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = b * 100 + d - 4800 + m // 10
    return (day, month, year)


def _new_moon(k: int) -> float:
    """1900-01-01 이후 k번째 삭(新月)의 율리우스일(UT). Meeus 근사."""
    T = k / 1236.85
    T2 = T * T
    T3 = T2 * T
    dr = _PI / 180
    jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * T2 - 0.000000155 * T3
    jd1 += 0.00033 * math.sin((166.56 + 132.87 * T - 0.009173 * T2) * dr)
    M = 359.2242 + 29.10535608 * k - 0.0000333 * T2 - 0.00000347 * T3
    Mpr = 306.0253 + 385.81691806 * k + 0.0107306 * T2 + 0.00001236 * T3
    F = 21.2964 + 390.67050646 * k - 0.0016528 * T2 - 0.00000239 * T3
    c1 = (0.1734 - 0.000393 * T) * math.sin(M * dr) + 0.0021 * math.sin(2 * dr * M)
    c1 = c1 - 0.4068 * math.sin(Mpr * dr) + 0.0161 * math.sin(dr * 2 * Mpr)
    c1 = c1 - 0.0004 * math.sin(dr * 3 * Mpr)
    c1 = c1 + 0.0104 * math.sin(dr * 2 * F) - 0.0051 * math.sin(dr * (M + Mpr))
    c1 = c1 - 0.0074 * math.sin(dr * (M - Mpr)) + 0.0004 * math.sin(dr * (2 * F + M))
    c1 = c1 - 0.0004 * math.sin(dr * (2 * F - M)) - 0.0006 * math.sin(dr * (2 * F + Mpr))
    c1 = c1 + 0.0010 * math.sin(dr * (2 * F - Mpr)) + 0.0005 * math.sin(dr * (2 * Mpr + M))
    if T < -11:
        deltat = 0.001 + 0.000839 * T + 0.0002261 * T2 - 0.00000845 * T3 - 0.000000081 * T * T3
    else:
        deltat = -0.000278 + 0.000265 * T + 0.000262 * T2
    return jd1 + c1 - deltat


def _sun_longitude(jdn: float) -> float:
    """율리우스일(UT) 기준 태양 황경(라디안, 0~2π)."""
    T = (jdn - 2451545.0) / 36525
    T2 = T * T
    dr = _PI / 180
    M = 357.52910 + 35999.05030 * T - 0.0001559 * T2 - 0.00000048 * T * T2
    L0 = 280.46645 + 36000.76983 * T + 0.0003032 * T2
    dl = (1.914600 - 0.004817 * T - 0.000014 * T2) * math.sin(dr * M)
    dl = dl + (0.019993 - 0.000101 * T) * math.sin(dr * 2 * M) + 0.000290 * math.sin(dr * 3 * M)
    ll = (L0 + dl) * dr
    # ★ 반드시 floor(−∞ 방향). 2000년 이전은 L0 가 음수라 int(0 방향 절삭)이면
    #   태양황경이 어긋나 中氣/윤달 판정이 틀어진다(원 알고리즘의 INT=Math.floor).
    ll = ll - _PI * 2 * math.floor(ll / (_PI * 2))
    return ll


def _get_sun_longitude(day_number: int, tz: float) -> int:
    """현지 자정 기준 태양 황경을 30° 구간(0~11)으로. (中氣 판정용)"""
    return math.floor(_sun_longitude(day_number - 0.5 - tz / 24) / _PI * 6)


def _get_new_moon_day(k: int, tz: float) -> int:
    """k번째 삭이 드는 현지 양력일(정수 적일)."""
    return math.floor(_new_moon(k) + 0.5 + tz / 24)


def _get_lunar_month_11(yy: int, tz: float) -> int:
    """그 해 음력 11월(冬至가 드는 달) 초하루의 적일."""
    off = jd_from_date(31, 12, yy) - 2415021
    k = math.floor(off / 29.530588853)
    nm = _get_new_moon_day(k, tz)
    sun_long = _get_sun_longitude(nm, tz)
    if sun_long >= 9:
        nm = _get_new_moon_day(k - 1, tz)
    return nm


def _get_leap_month_offset(a11: int, tz: float) -> int:
    k = math.floor((a11 - 2415021.076998695) / 29.530588853 + 0.5)
    last = 0
    i = 1
    arc = _get_sun_longitude(_get_new_moon_day(k + i, tz), tz)
    while True:
        last = arc
        i += 1
        arc = _get_sun_longitude(_get_new_moon_day(k + i, tz), tz)
        if not (arc != last and i < 14):
            break
    return i - 1


def solar_to_lunar(dd: int, mm: int, yy: int, tz: float = 7.0) -> tuple[int, int, int, bool]:
    """양력 → 음력 (lunar_day, lunar_month, lunar_year, is_leap)."""
    day_number = jd_from_date(dd, mm, yy)
    k = math.floor((day_number - 2415021.076998695) / 29.530588853)
    month_start = _get_new_moon_day(k + 1, tz)
    if month_start > day_number:
        month_start = _get_new_moon_day(k, tz)
    a11 = _get_lunar_month_11(yy, tz)
    b11 = a11
    if a11 >= month_start:
        lunar_year = yy
        a11 = _get_lunar_month_11(yy - 1, tz)
    else:
        lunar_year = yy + 1
        b11 = _get_lunar_month_11(yy + 1, tz)
    lunar_day = day_number - month_start + 1
    diff = math.floor((month_start - a11) / 29)
    lunar_leap = False
    lunar_month = diff + 11
    if b11 - a11 > 365:
        leap_month_diff = _get_leap_month_offset(a11, tz)
        if diff >= leap_month_diff:
            lunar_month = diff + 10
            if diff == leap_month_diff:
                lunar_leap = True
    if lunar_month > 12:
        lunar_month -= 12
    if lunar_month >= 11 and diff < 4:
        lunar_year -= 1
    return (lunar_day, lunar_month, lunar_year, lunar_leap)


def lunar_to_solar(
    lunar_day: int, lunar_month: int, lunar_year: int, is_leap: bool, tz: float = 7.0
) -> tuple[int, int, int]:
    """음력 → 양력 (dd, mm, yy). 존재하지 않는 윤달 입력 시 (0,0,0)."""
    if lunar_month < 11:
        a11 = _get_lunar_month_11(lunar_year - 1, tz)
        b11 = _get_lunar_month_11(lunar_year, tz)
    else:
        a11 = _get_lunar_month_11(lunar_year, tz)
        b11 = _get_lunar_month_11(lunar_year + 1, tz)
    k = math.floor(0.5 + (a11 - 2415021.076998695) / 29.530588853)
    off = lunar_month - 11
    if off < 0:
        off += 12
    if b11 - a11 > 365:
        leap_off = _get_leap_month_offset(a11, tz)
        leap_month = leap_off - 2
        if leap_month < 0:
            leap_month += 12
        if is_leap and lunar_month != leap_month:
            return (0, 0, 0)  # 그 해 그 달엔 윤달 없음
        elif is_leap or off >= leap_off:
            off += 1
    month_start = _get_new_moon_day(k + off, tz)
    return jd_to_date(month_start + lunar_day - 1)
