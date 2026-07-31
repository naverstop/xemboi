"""사주 명식 CLI.

사용:
  python -m backend.app.saju.cli --birth 1990-03-15 --time 14:30
  python -m backend.app.saju.cli --birth 1990-03-15 --time 14:30 --calendar lunar --leap
  python -m backend.app.saju.cli --birth 1990-03-15 --gender female --true-solar
  python -m backend.app.saju.cli --birth 1990-03-15 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, time

from .engine import build_chart
from .types import BirthInput, CalendarType, Gender


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _parse_time(s: str | None) -> time | None:
    if not s:
        return None
    parts = s.split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    return time.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="사주 명식 계산")
    ap.add_argument("--birth", required=True, help="생년월일 YYYY-MM-DD")
    ap.add_argument("--time", help="태어난 시각 HH:MM (생략시 시주 미상)")
    ap.add_argument("--calendar", choices=["solar", "lunar"], default="solar")
    ap.add_argument("--leap", action="store_true", help="음력 윤달")
    ap.add_argument("--gender", choices=["male", "female"], default="male")
    ap.add_argument("--true-solar", action="store_true", help="진태양시 보정(서울 -32분)")
    ap.add_argument("--no-daewoon", action="store_true")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args(argv)

    birth = BirthInput(
        birth_date=_parse_date(args.birth),
        birth_time=_parse_time(args.time),
        calendar=CalendarType(args.calendar),
        is_leap_month=args.leap,
        gender=Gender(args.gender),
        apply_true_solar_time=args.true_solar,
    )

    chart = build_chart(birth, with_daewoon=not args.no_daewoon)

    if args.json:
        print(chart.model_dump_json(indent=2))
        return 0

    print(chart.pretty())

    if chart.daewoon:
        d = chart.daewoon
        print(f"[대운] {d.direction} 시작 {d.start_age}세")
        for e in d.entries:
            print(f"  {e.start_age:>3}세  {e.pillar.gz}")

    tg = chart.ten_gods
    print(f"\n[십성]")
    print(f"  년간:{tg.year_stem}  월간:{tg.month_stem}  시간:{tg.hour_stem or '-'}")
    print(f"  년지:{tg.year_branch}  월지:{tg.month_branch}  일지:{tg.day_branch}  "
          f"시지:{tg.hour_branch or '-'}")

    print(f"\n[지장간]")
    for k, v in chart.hidden_stems.items():
        print(f"  {k} : {', '.join(v)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
