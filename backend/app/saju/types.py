"""사주 도메인 데이터 모델 (Pydantic v2)."""
from __future__ import annotations

from datetime import date, time
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CalendarType(str, Enum):
    SOLAR = "solar"   # 양력
    LUNAR = "lunar"   # 음력


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class BirthInput(BaseModel):
    """사주 계산 입력."""
    birth_date: date
    birth_time: time | None = None        # None이면 시주는 미상(時不明)
    calendar: CalendarType = CalendarType.SOLAR
    is_leap_month: bool = False           # 음력 윤달 여부
    gender: Gender = Gender.MALE
    # 진태양시 보정. 기본 False: 표준시 그대로.
    #   보정량 = (출생지 경도 − 당시 표준자오선)×4분. 표준자오선은 출생일 기준 자동(역사적).
    apply_true_solar_time: bool = False
    birth_longitude: float | None = None  # 출생지 경도(°E). None이면 서울 기본.
    apply_equation_of_time: bool = False  # 균시차 반영(진태양시 정밀)
    timezone_offset_min: int = 540        # KST = UTC+9 = 540
    # 자시(子時) 관법: 23:00~24:00 출생 처리
    #   yaja(야자시): 일주=당일, 시주 천간=익일 일간 기준 (현 기본·정통 야자시법)
    #   jeongja(정자시): 23:00부터 일주·시주 모두 익일 기준
    night_zi_mode: Literal["yaja", "jeongja"] = "yaja"
    # 로케일. ko=한국(sxtwl 음력·KST·서울경도), vi=베트남(호응옥득 음력·ICT·하노이경도).
    # 기본 ko → 기존 한국 계산 경로 완전 불변.
    locale: Literal["ko", "vi"] = "ko"

    @model_validator(mode="after")
    def _check(self):
        # 양력엔 윤달 개념이 없음 → 모순 입력(프론트의 양력 전환 후 잔류값 등)은 거부 대신
        # 정규화(False)로 흡수해 422 세션실패를 원천 차단(R2/R3 근본차단).
        if self.calendar != CalendarType.LUNAR:
            self.is_leap_month = False
        elif self.is_leap_month:
            # 음력 윤달: 그 해·월에 실제로 윤달이 존재하는지 검증. 없으면 조용히 평달 폴백
            # (=무경고 오답)하므로 명시적 오류로 승격(R1). 로케일별 역법 엔진으로 검증.
            has_leap: bool
            if self.locale == "vi":
                from .hongoc_duc import lunar_to_solar  # 베트남 음력(UTC+7)
                has_leap = lunar_to_solar(
                    self.birth_date.day, self.birth_date.month, self.birth_date.year, True, 7.0
                ) != (0, 0, 0)
            else:
                import sxtwl  # 중국·한국 음력(UTC+8)
                _d = sxtwl.fromLunar(self.birth_date.year, self.birth_date.month, self.birth_date.day, True)
                has_leap = bool(_d.isLunarLeap())
            if not has_leap:
                raise ValueError(
                    f"{self.birth_date.year}년 음력 {self.birth_date.month}월에는 윤달이 없습니다. "
                    f"'윤달'을 끄고 평달로 입력해 주세요."
                )
        return self


class Pillar(BaseModel):
    """주(柱) 하나 = 천간 + 지지."""
    stem: str = Field(..., description="천간 한자 (예: 甲)")
    branch: str = Field(..., description="지지 한자 (예: 子)")

    @property
    def gz(self) -> str:
        return f"{self.stem}{self.branch}"

    def __str__(self) -> str:
        return self.gz


class FourPillars(BaseModel):
    """사주 4주."""
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar | None = None  # 시주 미상시 None

    @property
    def day_master(self) -> str:
        """일간(日干) — 사주의 주체."""
        return self.day.stem

    def all_stems(self) -> list[str]:
        out = [self.year.stem, self.month.stem, self.day.stem]
        if self.hour:
            out.append(self.hour.stem)
        return out

    def all_branches(self) -> list[str]:
        out = [self.year.branch, self.month.branch, self.day.branch]
        if self.hour:
            out.append(self.hour.branch)
        return out


class WuxingDistribution(BaseModel):
    """오행 분포 (개수). 천간 + 지지 + 지장간 모두 합산."""
    wood: int = 0   # 木
    fire: int = 0   # 火
    earth: int = 0  # 土
    metal: int = 0  # 金
    water: int = 0  # 水

    def total(self) -> int:
        return self.wood + self.fire + self.earth + self.metal + self.water

    def as_dict_ko(self) -> dict[str, int]:
        return {"목": self.wood, "화": self.fire, "토": self.earth, "금": self.metal, "수": self.water}


class TenGodAssignment(BaseModel):
    """각 주의 천간/지지에 대한 십성 매핑."""
    year_stem: str
    month_stem: str
    hour_stem: str | None
    year_branch: str    # 지지 정기(正氣) 기준
    month_branch: str
    day_branch: str
    hour_branch: str | None


class JohuYongsin(BaseModel):
    """조후용신(調候用神) — 궁통보감(난강망) 일간×월지 결정값.

    월령이 결정하는 계절의 한난조습(寒暖燥濕)을 일간 기준으로 중화하는 천간.
    겨울(亥子丑월)·여름(巳午未월)생은 조후를 '먼저' 본다(is_climate_priority).
    """
    primary: str                                          # 정조후용신 천간 한자 (예: 丙)
    supporting: list[str] = Field(default_factory=list)   # 보조용신 천간들(우선순위순)
    season: str                                           # 봄/여름/가을/겨울
    climate: str                                          # 寒(겨울)/暖(여름)/평
    is_climate_priority: bool = False                     # 겨울·여름 → 조후 우선
    note: str = ""                                        # 근거 한 줄(계절 한난)
    source: str = "궁통보감 조후용신"


class DaewoonEntry(BaseModel):
    """대운 한 구간."""
    start_age: int          # 만 나이 기준 시작
    pillar: Pillar
    direction: Literal["forward", "backward"]


class Daewoon(BaseModel):
    """대운 전체."""
    direction: Literal["forward", "backward"]   # 순행/역행
    start_age: float                            # 대운수(시작 만나이, 소수 포함)
    entries: list[DaewoonEntry]


class SajuChart(BaseModel):
    """사주 종합 결과 (사주명식)."""
    input: BirthInput
    solar_date: date                # 양력으로 정규화된 생일
    solar_time: time | None
    lunar_date: date                # 음력 (양력 입력시 변환됨)
    is_leap_month: bool
    pillars: FourPillars
    wuxing: WuxingDistribution
    wuxing_branch_only: WuxingDistribution   # 지지 본기만
    ten_gods: TenGodAssignment
    day_master_element: str         # 일간의 오행
    day_master_strength: Literal["strong", "weak", "neutral"]
    daewoon: Daewoon | None = None
    hidden_stems: dict[str, list[str]] = Field(default_factory=dict)   # 위치(년지/월지/일지/시지)별 지장간
    twelve_life: dict[str, str] = Field(default_factory=dict)          # 위치(년/월/일/시)별 십이운성
    twelve_sinsal: dict[str, str] = Field(default_factory=dict)        # 위치별 십이신살(년지 기준)
    gongmang: list[str] = Field(default_factory=list)                  # 공망 2지지(일주 기준)
    napeum: dict[str, str] = Field(default_factory=dict)               # 위치별 납음(納音) 한글명
    saryeong: str = ""                                                 # 사령(司令) 천간(월률분야)
    johu_yongsin: JohuYongsin | None = None                            # 조후용신(궁통보감 일간×월지)

    def pretty(self) -> str:
        """원광만세력 스타일 간단 출력. 독음은 로케일(ko 한글 / vi 한월음)."""
        from .constants import STEM_TO_WUXING, branch_reading, stem_reading

        loc = self.input.locale

        def cell(p: Pillar | None) -> tuple[str, str]:
            if p is None:
                return ("?", "?")
            return (f"{p.stem}({stem_reading(p.stem, loc)})", f"{p.branch}({branch_reading(p.branch, loc)})")

        cols = [cell(self.pillars.hour), cell(self.pillars.day),
                cell(self.pillars.month), cell(self.pillars.year)]
        header = "   時      日      月      年"
        line_stem = "  " + "  ".join(f"{c[0]:<6}" for c in cols)
        line_brch = "  " + "  ".join(f"{c[1]:<6}" for c in cols)

        wx = self.wuxing.as_dict_ko()
        wx_str = "  ".join(f"{k}:{v}" for k, v in wx.items())

        return (
            f"[사주명식]\n"
            f"양력 {self.solar_date} {self.solar_time or '시간미상'}  "
            f"음력 {self.lunar_date}{' (윤달)' if self.is_leap_month else ''}  "
            f"성별 {self.input.gender.value}\n"
            f"{header}\n{line_stem}\n{line_brch}\n"
            f"일간: {self.pillars.day_master}({stem_reading(self.pillars.day_master, loc)}) "
            f"— {self.day_master_element} ({self.day_master_strength})\n"
            f"오행: {wx_str}\n"
        )
