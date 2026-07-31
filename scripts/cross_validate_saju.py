"""sxtwl 기반 build_chart 결과 vs lunar-python 결과 cross-validation.

원광만세력 자동 호출이 불가능하여, 독립 구현체(lunar-python; 중국에서
가장 널리 쓰이는 만세력 라이브러리)를 기준으로 100건 랜덤 케이스를 자동 비교한다.

두 엔진이 일치하면 sxtwl 기반 본 프로젝트 엔진의 신뢰도가 확보된다.
(원광만세력도 결국 동일한 천문력/절기 알고리즘을 사용하므로
 lunar-python과 sxtwl이 일치하면 원광과도 일치할 가능성이 매우 높다.)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, time, timedelta
from pathlib import Path

from lunar_python import Solar  # type: ignore

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender


def _ours(birth_d: date, birth_t: time) -> dict:
    chart = build_chart(
        BirthInput(
            birth_date=birth_d,
            birth_time=birth_t,
            calendar=CalendarType("solar"),
            gender=Gender("male"),
            apply_true_solar_time=False,
        )
    )
    p = chart.pillars
    return {
        "year": p.year.gz,
        "month": p.month.gz,
        "day": p.day.gz,
        "hour": p.hour.gz if p.hour else None,
    }


def _reference(birth_d: date, birth_t: time) -> dict:
    s = Solar.fromYmdHms(
        birth_d.year, birth_d.month, birth_d.day,
        birth_t.hour, birth_t.minute, 0,
    )
    ec = s.getLunar().getEightChar()
    return {
        "year": ec.getYear(),
        "month": ec.getMonth(),
        "day": ec.getDay(),
        "hour": ec.getTime(),
    }


def _gen_random_cases(n: int, seed: int) -> list[tuple[date, time]]:
    rng = random.Random(seed)
    out = []
    start = date(1920, 1, 1)
    span_days = (date(2025, 12, 31) - start).days
    for _ in range(n):
        d = start + timedelta(days=rng.randrange(span_days))
        # 시·분 랜덤 — 자시(23~01) 포함 전 범위
        t = time(rng.randrange(0, 24), rng.choice([0, 15, 30, 45]))
        out.append((d, t))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260601)
    ap.add_argument("--out", default="data/eval/cross_validate_saju.jsonl")
    args = ap.parse_args(argv)

    cases = _gen_random_cases(args.n, args.seed)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    matches = {"year": 0, "month": 0, "day": 0, "hour": 0}
    full_match = 0
    mismatches: list[dict] = []

    with out_path.open("w", encoding="utf-8") as f:
        for i, (d, t) in enumerate(cases, 1):
            ours = _ours(d, t)
            ref = _reference(d, t)
            per = {k: ours[k] == ref[k] for k in matches}
            for k, v in per.items():
                if v:
                    matches[k] += 1
            if all(per.values()):
                full_match += 1
            else:
                mismatches.append({
                    "i": i, "date": d.isoformat(), "time": t.isoformat(timespec="minutes"),
                    "ours": ours, "ref": ref,
                    "diff": {k: f"{ours[k]}≠{ref[k]}" for k, v in per.items() if not v},
                })
            f.write(json.dumps({
                "i": i, "date": d.isoformat(), "time": t.isoformat(timespec="minutes"),
                "ours": ours, "ref": ref, "match": per,
            }, ensure_ascii=False) + "\n")

    print(f"=== Cross-Validation: sxtwl(build_chart) vs lunar-python ===")
    print(f"총 케이스: {args.n} (seed={args.seed}, range=1920~2025)")
    print(f"  Year 일치  : {matches['year']:>3}/{args.n}  ({matches['year']/args.n*100:.1f}%)")
    print(f"  Month 일치 : {matches['month']:>3}/{args.n}  ({matches['month']/args.n*100:.1f}%)")
    print(f"  Day 일치   : {matches['day']:>3}/{args.n}  ({matches['day']/args.n*100:.1f}%)")
    print(f"  Hour 일치  : {matches['hour']:>3}/{args.n}  ({matches['hour']/args.n*100:.1f}%)")
    print(f"  4기둥 전체 일치 : {full_match}/{args.n}  ({full_match/args.n*100:.1f}%)")
    print(f"  결과 파일 : {out_path}")

    if mismatches:
        print(f"\n[불일치 {len(mismatches)}건 상세 (최대 20건)]")
        for m in mismatches[:20]:
            print(f"  #{m['i']:>3} {m['date']} {m['time']}  diff={m['diff']}")
        if len(mismatches) > 20:
            print(f"  ... 외 {len(mismatches)-20}건은 {out_path} 참조")
        return 1
    print("\n✅ 전체 케이스 일치 — sxtwl 엔진 알고리즘 신뢰도 확보")
    return 0


if __name__ == "__main__":
    sys.exit(main())
