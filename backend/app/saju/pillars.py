"""사주 4주(년/월/일/시) 계산 — sxtwl 래퍼."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import sxtwl

from .constants import (
    EARTHLY_BRANCHES,
    HEAVENLY_STEMS,
)
from .types import BirthInput, CalendarType, FourPillars, Pillar

import math

try:  # 서머타임·역사적 표준시(127.5°E) 자동 보정용 — IANA tz(권위 데이터)
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo("Asia/Seoul")
except Exception:  # noqa: BLE001
    _KST = None

# 출생지 경도 기본값(서울). 진태양시 보정 시 사용. 표준자오선과의 차 × 4분/도.
DEFAULT_LONGITUDE = 126.98
# 베트남 기본 경도(하노이). vi 로케일 진태양시 기본값. 표준자오선 105°E(UTC+7).
VN_DEFAULT_LONGITUDE = 105.85


def _civil_std_offset_h(d: date) -> float:
    """그 시기 한국 표준시(서머타임 제외)의 UTC offset 시간. (출처: 위키 '한국 표준시')
    1908-04-01~1911: +8.5(127.5°E) / 1912~1954-03-20: +9 / 1954-03-21~1961-08-09: +8.5 / 이후: +9."""
    if d < date(1912, 1, 1):
        return 8.5
    if d < date(1954, 3, 21):
        return 9.0
    if d < date(1961, 8, 10):
        return 8.5
    return 9.0


def _vn_civil_std_offset_h(d: date) -> float:
    """그 시기 베트남 표준시 UTC offset(시간). 출처: IANA tz Asia/Ho_Chi_Minh(남부/사이공).
    베트남은 현대에 서머타임이 없어 이 값이 곧 실제 offset이다(DST 제거항 0).
    ⚠ 북부(하노이) 전시(1954~75) 이력은 IANA에 미수록 — 그 시기·지역 출생자는 시주 오차 가능.
    ~1911-05: +7:06:30(PLMT) / ~1942-12: +7 / ~1945-03: +8 / ~1945-09: +9(일제) /
    ~1947-04: +7 / ~1955-07: +8 / ~1959-12: +7 / ~1975-06-13: +8(남베트남) / 이후: +7."""
    if d < date(1911, 5, 1):
        return 7.1083  # +7:06:30
    if d < date(1942, 12, 31):
        return 7.0
    if d < date(1945, 3, 14):
        return 8.0
    if d < date(1945, 9, 2):
        return 9.0
    if d < date(1947, 4, 1):
        return 7.0
    if d < date(1955, 7, 1):
        return 8.0
    if d < date(1959, 12, 31):
        return 7.0
    if d < date(1975, 6, 13):
        return 8.0
    return 7.0


def _kst_utcoffset_h(solar_d: date, t: time) -> float:
    """그 일시의 실제 한국 UTC offset(서머타임 포함). IANA tz 사용, 실패 시 표준시로 대체."""
    if _KST is None:
        return _civil_std_offset_h(solar_d)
    try:
        off = datetime(solar_d.year, solar_d.month, solar_d.day, t.hour, t.minute, tzinfo=_KST).utcoffset()
        return off.total_seconds() / 3600.0 if off else _civil_std_offset_h(solar_d)
    except Exception:  # noqa: BLE001
        return _civil_std_offset_h(solar_d)


def _equation_of_time_min(d: date) -> float:
    """균시차(분) 근사 — 진태양시(시태양시) = 평균태양시 + 균시차. NOAA 약식."""
    n = d.timetuple().tm_yday
    b = math.radians(360.0 * (n - 81) / 364.0)
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def _to_solar(birth: BirthInput) -> date:
    """입력을 양력 date 로 정규화. 음력은 로케일 역법으로 변환(vi=호응옥득 UTC+7)."""
    if birth.calendar == CalendarType.SOLAR:
        return birth.birth_date
    if birth.locale == "vi":
        # 베트남 음력(Âm lịch, UTC+7) → 양력. 중국·한국 음력과 경계일에서 하루 어긋날 수 있음.
        from .hongoc_duc import lunar_to_solar
        dd, mm, yy = lunar_to_solar(
            birth.birth_date.day, birth.birth_date.month, birth.birth_date.year,
            birth.is_leap_month, 7.0,
        )
        return date(yy, mm, dd)
    # 음력 → 양력 (중국·한국, sxtwl/UTC+8)
    d = sxtwl.fromLunar(
        birth.birth_date.year,
        birth.birth_date.month,
        birth.birth_date.day,
        birth.is_leap_month,
    )
    return date(d.getSolarYear(), d.getSolarMonth(), d.getSolarDay())


def _adjust_time(birth: BirthInput, solar_d: date) -> tuple[date, time | None, time | None]:
    """시각 보정 → (표준일, 표준시각, 진태양시각). 시간 없으면 (solar_d, None, None).

    ① 서머타임 자동 제거(항상): 기록 시각(현지 시계) → 그 시기 표준시. 이건 '실제 표준시'라
       일/월/년주·야자시(일 경계) 기준이 된다(1948~51·55~60·87~88 서머타임 출생자 시 어긋남 교정).
    ② 진태양시(옵션): 표준시 → 현지 태양시 = 경도(+균시차) 보정.

    ★ 2026-07 전문가 관법 결정: **진태양시(경도 보정)는 시주(時)에만 적용하고 일주(日)의 날짜
      경계를 넘기지 않는다.** 그래서 ②(경도) 보정은 '진태양시각'에만 반영하고, 일/월/년주와 야자시
      판정은 '표준시각/표준일'을 쓴다. (종전엔 −32분 경도보정이 00:30을 전날로 굴려 일주가 하루
      밀리는 재발 버그가 있었음 — 실측 00:30 표본 48/48 시프트.)
    로케일: vi(베트남)는 현대 서머타임 없음 → 제거항 0, 표준자오선 105°E·기본경도 하노이."""
    if birth.birth_time is None:
        return solar_d, None, None
    dt = datetime.combine(solar_d, birth.birth_time)

    if birth.locale == "vi":
        # 베트남: 현대 서머타임 없음 → off==civil(제거항 0). 표준자오선 105°E(civil×15).
        civil_h = _vn_civil_std_offset_h(solar_d)
        off_h = civil_h
        default_lon = VN_DEFAULT_LONGITUDE
    else:
        off_h = _kst_utcoffset_h(solar_d, birth.birth_time)
        civil_h = _civil_std_offset_h(solar_d)
        default_lon = DEFAULT_LONGITUDE
    dst_min = -(off_h - civil_h) * 60.0        # ① 서머타임 제거(표준시 환산) — 일/월/년주 기준
    std_dt = dt + timedelta(minutes=round(dst_min)) if dst_min else dt

    solar_dt = std_dt
    if birth.apply_true_solar_time:             # ② 경도 보정 — 진태양시각(시주 전용)에만
        lon = birth.birth_longitude if birth.birth_longitude is not None else default_lon
        ts_min = (lon - civil_h * 15.0) * 4.0
        if birth.apply_equation_of_time:
            ts_min += _equation_of_time_min(solar_d)
        if ts_min:
            solar_dt = std_dt + timedelta(minutes=round(ts_min))
    return std_dt.date(), std_dt.time(), solar_dt.time()


def _gz_to_pillar(gz) -> Pillar:
    return Pillar(stem=HEAVENLY_STEMS[gz.tg], branch=EARTHLY_BRANCHES[gz.dz])


def compute_pillars(birth: BirthInput) -> tuple[FourPillars, date, time | None, date, bool]:
    """입력 → (4주, 정규화 양력일, 정규화 시간, 음력일, 윤달여부)."""
    solar_d = _to_solar(birth)
    # 표준일/표준시각 = 일·월·년주·야자시 기준(진태양시 미반영). 진태양시각 = 시주 전용.
    std_d, std_t, solar_t = _adjust_time(birth, solar_d)

    # 자시(子時, 23:00~24:00) 관법 처리. 일 경계이므로 '표준시각(std_t)' 기준으로 판정한다
    # (진태양시가 일주를 밀지 않게 하는 관법 결정 — _adjust_time 주석 참조).
    #   - 야자시(yaja, 기본): 일주는 당일(자정 경계) 유지, 시주 천간은 익일 일간 기준.
    #       sxtwl.getHourGZ(23) 가 익일 일간으로 자시 천간을 계산 → 정통 야자시법과 일치.
    #   - 정자시(jeongja): 23:00부터 일주·시주 모두 익일 기준 → 일주도 다음날로 굴림.
    is_late_zi = std_t is not None and std_t.hour == 23
    if is_late_zi and birth.night_zi_mode == "jeongja":
        eff = std_d + timedelta(days=1)               # 23시 → 익일로 굴림
        day = sxtwl.fromSolar(eff.year, eff.month, eff.day)
        year_p = _gz_to_pillar(day.getYearGZ())
        month_p = _gz_to_pillar(day.getMonthGZ())
        day_p = _gz_to_pillar(day.getDayGZ())         # 익일 일주
        hour_p: Pillar | None = _gz_to_pillar(day.getHourGZ(0))  # 익일 자시(子時)
    else:
        day = sxtwl.fromSolar(std_d.year, std_d.month, std_d.day)   # 일·월·년주 = 표준일 기준
        year_p = _gz_to_pillar(day.getYearGZ())   # 입춘 기준
        month_p = _gz_to_pillar(day.getMonthGZ()) # 절입 기준
        day_p = _gz_to_pillar(day.getDayGZ())     # 자정 기준
        hour_p = None
        if solar_t is not None:
            # 시주(時)만 진태양시각 기준. sxtwl.getHourGZ(23) 은 자시 천간을 익일 일간 기준(야자시법).
            hour_p = _gz_to_pillar(day.getHourGZ(solar_t.hour))

    # 음력일을 그레고리력 date 컨테이너에 담는다(표시용). 음력 대월 29·30일이 그레고리력 해당 월에
    # 없는 날이면 ValueError — 표시용 음력일만 그 달의 마지막 유효일로 클램프(사주 계산 무영향).
    if birth.locale == "vi":
        # 베트남 음력 표시는 호응옥득(UTC+7)로 — day 가 대표하는 양력일 기준(자시 굴림 반영).
        from .hongoc_duc import solar_to_lunar
        _ld, _lm, _ly = None, None, None
        _ld, _lm, _ly, is_leap = solar_to_lunar(
            day.getSolarDay(), day.getSolarMonth(), day.getSolarYear(), 7.0
        )
    else:
        _ly, _lm, _ld = day.getLunarYear(), day.getLunarMonth(), day.getLunarDay()
        is_leap = bool(day.isLunarLeap())
    while _ld > 28:
        try:
            lunar_d = date(_ly, _lm, _ld)
            break
        except ValueError:
            _ld -= 1
    else:
        lunar_d = date(_ly, _lm, _ld)

    return (
        FourPillars(year=year_p, month=month_p, day=day_p, hour=hour_p),
        std_d,        # 정규화 양력일 = 표준일(일주 기준) — 대운·표시에 사용
        solar_t,      # 정규화 시간 = 진태양시각(시주 기준)
        lunar_d,
        is_leap,
    )
