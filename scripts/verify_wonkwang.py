"""원광만세력 대조용 검증 스크립트.

원광만세력 (https://wonkwangdigital.com) 화면과 동일한 항목 배열로 출력해
사용자가 한눈에 비교/체크할 수 있도록 한다.

사용 예:
  # 단일 케이스
  python -m scripts.verify_wonkwang --birth 1990-03-15 --time 14:30 --calendar solar --gender male

  # 배치 (JSONL: birth_date, birth_time, calendar, gender, is_leap_month, label)
  python -m scripts.verify_wonkwang --batch ml/eval/datasets/wonkwang_cases.jsonl

  # 대조 결과 기록 (사용자가 원광 값을 채워 넣은 후)
  python -m scripts.verify_wonkwang --batch ml/eval/datasets/wonkwang_cases.jsonl --check

배치 JSONL 한 줄 예:
  {"label":"본인","birth_date":"1990-03-15","birth_time":"14:30","calendar":"solar","gender":"male",
   "expected":{"year":"庚午","month":"己卯","day":"己卯","hour":"辛未"}}
expected 가 없으면 출력만, 있으면 비교 결과(O/X) 표시.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, time
from pathlib import Path

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender


def _to_input(row: dict) -> BirthInput:
    bt = row.get("birth_time")
    return BirthInput(
        birth_date=date.fromisoformat(row["birth_date"]),
        birth_time=time.fromisoformat(bt) if bt else None,
        calendar=CalendarType(row.get("calendar", "solar")),
        is_leap_month=bool(row.get("is_leap_month", False)),
        gender=Gender(row.get("gender", "male")),
        apply_true_solar_time=bool(row.get("apply_true_solar_time", False)),
    )


def _format_case(label: str, row: dict, chart, expected: dict | None) -> tuple[str, dict]:
    """원광만세력 화면과 동일한 핵심 4기둥 + 일주/대운 정보를 출력 + 비교 결과 반환."""
    p = chart.pillars
    got = {
        "year": p.year.gz,
        "month": p.month.gz,
        "day": p.day.gz,
        "hour": p.hour.gz if p.hour else None,
    }

    cal = row.get("calendar", "solar")
    bt = row.get("birth_time") or "시미상"
    leap = " (윤달)" if row.get("is_leap_month") else ""
    header = f"=== [{label}] {row['birth_date']} {bt} | {cal}{leap} | {row.get('gender','male')} ==="

    lines = [header]
    lines.append(f"  생일변환:  양력 {chart.solar_date}  /  음력 {chart.lunar_date}"
                 f"{' (윤달)' if chart.is_leap_month else ''}  /  시각 {chart.solar_time or '-'}")
    lines.append("")
    lines.append("           시주    일주    월주    년주     ← 원광만세력 배치(오른→왼)")
    h = got['hour'] or '--'
    lines.append(f"  명식:    {h:<6} {got['day']:<6} {got['month']:<6} {got['year']:<6}")
    lines.append(f"  일간(本人) = {p.day.stem} ({chart.day_master_element})  "
                 f"강약 = {chart.day_master_strength}")
    lines.append(f"  오행수:  {chart.wuxing.as_dict_ko()}")

    tg = chart.ten_gods
    lines.append(f"  십성:    년간 {tg.year_stem} | 월간 {tg.month_stem} | "
                 f"시간 {tg.hour_stem or '-'} | 년지 {tg.year_branch} | "
                 f"월지 {tg.month_branch} | 일지 {tg.day_branch} | 시지 {tg.hour_branch or '-'}")

    if chart.daewoon:
        dw = chart.daewoon
        dir_ko = "순행" if dw.direction == "forward" else "역행"
        head = ", ".join(f"{e.start_age}세 {e.pillar.gz}" for e in dw.entries[:5])
        lines.append(f"  대운:    {dir_ko} / 대운수 {dw.start_age:.1f}세 / {head} ...")

    diff_report = {"label": label, "got": got, "expected": expected, "match": None}
    if expected is not None:
        mism = []
        for key in ("year", "month", "day", "hour"):
            exp = expected.get(key)
            g = got.get(key)
            if exp is None:
                continue
            if g != exp:
                mism.append(f"{key}: got={g} expected={exp}")
        if not mism:
            lines.append("  >>> 원광 대조: ✅ ALL MATCH")
            diff_report["match"] = True
        else:
            lines.append("  >>> 원광 대조: ❌ MISMATCH")
            for m in mism:
                lines.append(f"      - {m}")
            diff_report["match"] = False

    lines.append("")
    return "\n".join(lines), diff_report


def _print_single(args) -> int:
    row = {
        "birth_date": args.birth,
        "birth_time": args.time,
        "calendar": args.calendar,
        "is_leap_month": args.leap,
        "gender": args.gender,
        "apply_true_solar_time": args.true_solar,
    }
    chart = build_chart(_to_input(row))
    out, _ = _format_case("단일", row, chart, None)
    print(out)
    print("→ 위 명식을 원광만세력(https://wonkwangdigital.com)에 동일 조건으로 입력해 4기둥을 비교하세요.")
    return 0


def _run_batch(path: Path, check: bool) -> int:
    if not path.exists():
        print(f"[ERR] 배치 파일 없음: {path}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))

    total = 0
    matched = 0
    pending = 0
    mismatched: list[dict] = []

    for r in rows:
        chart = build_chart(_to_input(r))
        out, rep = _format_case(r.get("label", r.get("id", "?")), r, chart,
                                r.get("expected") if check else None)
        print(out)
        if check:
            total += 1
            if rep["match"] is True:
                matched += 1
            elif rep["match"] is False:
                mismatched.append(rep)
            else:
                pending += 1

    if check:
        print("=" * 70)
        print(f"  총 케이스: {total}  /  ✅ MATCH: {matched}  /  ❌ MISMATCH: {len(mismatched)}"
              f"  /  ⏳ expected 미입력: {pending}")
        if mismatched:
            print("\n[불일치 상세]")
            for m in mismatched:
                print(f"  - {m['label']}: got={m['got']}  expected={m['expected']}")
            return 1
        if pending and not matched:
            print("\n[안내] expected 값이 비어 있어 비교 불가. 원광 사이트에서 4기둥을 확인하여")
            print("       JSONL의 expected 항목에 {year,month,day,hour} 한자 갑자로 채워 넣으세요.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="원광만세력 대조 검증")
    ap.add_argument("--birth", help="단일 모드: 생년월일 YYYY-MM-DD")
    ap.add_argument("--time", help="단일 모드: HH:MM (생략 가능)")
    ap.add_argument("--calendar", choices=["solar", "lunar"], default="solar")
    ap.add_argument("--leap", action="store_true")
    ap.add_argument("--gender", choices=["male", "female"], default="male")
    ap.add_argument("--true-solar", action="store_true")
    ap.add_argument("--batch", help="배치 모드: JSONL 경로")
    ap.add_argument("--check", action="store_true",
                    help="배치 모드: expected 값과 비교하여 종료코드로 결과 표시")
    args = ap.parse_args(argv)

    if args.batch:
        return _run_batch(Path(args.batch), args.check)
    if args.birth:
        return _print_single(args)
    ap.error("--birth 또는 --batch 중 하나를 지정하세요.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
