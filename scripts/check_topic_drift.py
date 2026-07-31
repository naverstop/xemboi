# -*- coding: utf-8 -*-
"""답변 품질 검증 루틴 — 주제 이탈 + 과거연도/간지 환각을 실제 LLM 출력으로 점검.

전문가 피드백(취업운 상담 직후 '남자친구 언제?'에 답이 취업으로 흐르고 '2023년 계묘년'
같은 과거연도·간지를 들먹임)을 실제 파이프라인으로 재현·검증한다. Ollama(:11434) 필요.

실행: .venv\\Scripts\\python.exe -m scripts.check_topic_drift
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def _scan(text: str) -> dict:
    cur = date.today().year
    # 본문에 등장한 4자리 연도 중 '과거'(올해 미만)
    years = [int(y) for y in re.findall(r"(20[0-3][0-9])\s*년", text)]
    past_years = sorted({y for y in years if y < cur})
    # 60간지 '○○년' 언급 — 올해/내년 간지만 허용, 그 외(예: 계묘년)는 환각
    GANJI = re.findall(
        r"([갑을병정무기경신임계][자축인묘진사오미신유술해])\s*년", text)
    # 올해/내년 정답 간지
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT

    def gz_of(yr: int) -> str:
        fp, *_ = compute_pillars(_BI(birth_date=date(yr, 6, 1), calendar=_CT.SOLAR))
        STEM = "갑을병정무기경신임계"; BR = "자축인묘진사오미신유술해"
        # compute_pillars 의 year pillar 한글 변환
        from backend.app.services.chat_service import _gz_ko
        return _gz_ko(fp.year).split("(")[0]
    allow = {gz_of(cur), gz_of(cur + 1)}
    wrong_ganji = sorted({g for g in GANJI if g not in allow})
    career = len(re.findall(r"취업|직장|이직|경력|커리어|승진|업무|면접|일자리", text))
    love = len(re.findall(r"연애|인연|이성|남자친구|남친|만남|관계|결혼|애정|짝", text))
    return {
        "past_years": past_years, "wrong_ganji": wrong_ganji,
        "career_terms": career, "love_terms": love,
        "allow_ganji": sorted(allow),
    }


def main() -> int:
    from backend.app.saju.engine import build_chart
    from backend.app.saju.types import BirthInput, CalendarType, Gender
    from backend.app.services import chat_service as cs

    bi = BirthInput(birth_date=date(1995, 5, 5), birth_time=None,
                    calendar=CalendarType.SOLAR, gender=Gender.FEMALE)
    chart = build_chart(bi)
    summary = cs._build_saju_summary(chart, bi)

    sys_content = cs._compose_sys_content(cs.SYSTEM_PROMPT, "standard", "normal")
    # 직전 대화(취업운) → 새 질문(남자친구)로 주제 전환 시나리오
    history = [
        {"role": "user", "content": "올해 취업운이 어떤가요?"},
        {"role": "assistant", "content": "올해는 직장과 경력 면에서 적극적으로 도전하면 좋은 흐름입니다. 면접과 이직 기회를 잘 살리세요."},
    ]
    question = "남자친구는 언제 생길까요?"
    user_prompt = cs._build_user_prompt(question, [], summary)
    msgs = [{"role": "system", "content": sys_content}, *history,
            {"role": "user", "content": user_prompt}]

    print(f"[검증] 오늘={date.today()} / 시나리오: 취업운 직후 '남자친구 언제?'\n")
    print("=== 1차(초안, exaone) 생성 중… ===")
    draft = (cs._call_ollama(msgs) or "").strip()
    d = _scan(draft)
    print(f"  과거연도={d['past_years']} 환각간지={d['wrong_ganji']} (허용간지={d['allow_ganji']}) "
          f"취업어={d['career_terms']} 연애어={d['love_terms']}")

    print("\n=== 2차(보강, qwen) 생성 중… ===")
    refined = cs._refine_with_qwen(
        question=question, draft=draft, saju_summary=summary,
        evidence=None, rag_context=None, dialect_instruction=None,
    )
    if refined:
        r = _scan(refined)
        print(f"  과거연도={r['past_years']} 환각간지={r['wrong_ganji']} (허용간지={r['allow_ganji']}) "
              f"취업어={r['career_terms']} 연애어={r['love_terms']}")
    else:
        r = d
        print("  (보강 None — 초안 유지)")

    # === 3차(외부 보강, Claude) — 키 있을 때만. 직전(qwen 또는 초안) 답변을 Claude로 보강 ===
    from backend.app.services import external_llm as ex
    after_internal = refined or draft
    claude_out = None
    if ex.is_enabled():
        print("\n=== 3차(외부 보강, Claude) 생성 중… ===")
        claude_out = cs._claude_boost(
            question=question, draft=after_internal, saju_summary=summary,
            evidence=None, rag_context=None, dialect_instruction=None,
        )
        if claude_out:
            c = _scan(claude_out)
            print(f"  과거연도={c['past_years']} 환각간지={c['wrong_ganji']} (허용간지={c['allow_ganji']}) "
                  f"취업어={c['career_terms']} 연애어={c['love_terms']}")
        else:
            print("  (Claude 보강 None — 직전 답변 유지)")
    else:
        print("\n=== 3차(외부 보강, Claude) — external_llm 비활성(키 없음) → 생략 ===")

    after_external = claude_out or after_internal

    # === 전체 재검증 게이트 — 내부+외부 보강 뒤 최종 답변에 결정적 시점 정제 적용 ===
    final = cs._scrub_stale_year_ganji(after_external)
    if final != after_external:
        print("\n[게이트] 과거연도·틀린 간지 감지 → 최종 정제 적용됨")
    fs = _scan(final)
    ok_year = not fs["past_years"]
    ok_ganji = not fs["wrong_ganji"]
    ok_topic = fs["love_terms"] >= fs["career_terms"]
    verdict = "PASS" if (ok_year and ok_ganji and ok_topic) else "FAIL"
    print("\n========================================")
    print(f"최종 판정: {verdict}")
    print(f"  과거연도 미언급: {ok_year} ({fs['past_years']})")
    print(f"  환각간지 없음:   {ok_ganji} ({fs['wrong_ganji']})")
    print(f"  주제(연애≥취업): {ok_topic} (연애 {fs['love_terms']} / 취업 {fs['career_terms']})")
    print("========================================")
    print("\n--- 최종 답변(앞 600자) ---")
    print(final[:600])
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
