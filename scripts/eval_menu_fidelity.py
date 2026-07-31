# -*- coding: utf-8 -*-
"""전 메뉴(사주·궁합·택일·작명·개명·아호) 명식 정합성 라이브 검증.

각 메뉴의 *실제* brief 구성 + 검증·교정 로직을 그대로 사용해
  exaone(1차) → qwen(보강) → 메뉴별 명식 검증·교정 → 표현정리
파이프라인을 돌리고, 최종 답변이 결정값과 일치하는지(=환각 0) 측정한다.

측정 항목(메뉴별):
  · 지지(地支)  : 답변의 년/월/일/시지가 명식(궁합=두 명식 union)과 일치  ← 모든 메뉴 검증
  · 일간(天干)  : 답변의 일간이 명식 일간과 일치                          ← 현재 chat만 검증
  · 세운(올해)  : '올해 ○○년' 류가 실제 세운(병오)과 일치                 ← chat만 주입

init = 1차+보강 직후(예방효과), final = 메뉴 검증·교정 후(목표 100%).
일간/세운은 '현행 production이 그 메뉴에서 검증/주입하는지'와 무관하게 *측정*해 갭을 드러낸다.

실행: python -m scripts.eval_menu_fidelity [--fast(=qwen생략)] [--no-rag] [--only 사주,궁합,...]
CPU 전용(exaone/qwen). 외부비용 0.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender
from backend.app.saju import naming as naming_engine
from backend.app.saju import taekil as taekil_engine
from backend.app.services import chat_service as cs, template_service
from backend.app.services import tool_service as ts
from backend.app.services import compat_service as cmp
from backend.app.repositories.models import ToolSession
from backend.app.core.db import get_session_factory

# ── 현재 세운(올해 간지) 결정값 — '올해 ○○년' 환각 측정 기준 ───────────────
def _current_sewoon_ko() -> str:
    from backend.app.saju.pillars import compute_pillars
    fp, *_ = compute_pillars(BirthInput(birth_date=date.today(), calendar=CalendarType.SOLAR))
    from backend.app.saju.constants import stem_korean, branch_korean
    return f"{stem_korean(fp.year.stem)}{branch_korean(fp.year.branch)}"  # 예: 병오

_SEWOON = _current_sewoon_ko()
_SEWOON_RE = re.compile(r"(올해|금년|이번\s*해|올\s*한\s*해)[^.\n]{0,18}?([갑을병정무기경신임계][자축인묘진사오미신유술해])")


def _verify_sewoon(answer: str) -> list[tuple[str, str, str]]:
    """'올해 ○○년'으로 적힌 세운이 실제(병오)와 다르면 환각."""
    out = []
    for m in (_SEWOON_RE.finditer(answer or "")):
        if m.group(2) != _SEWOON:
            out.append((m.group(1), m.group(2), _SEWOON))
    return out


def _verify_stem_multi(answer: str, stems: set[str]) -> list:
    """답변의 '일간 …(漢)'이 허용 천간집합(궁합=두 사람)에 없으면 불일치."""
    if not answer or not stems:
        return []
    for m in re.finditer("일간", answer):
        win = answer[m.end(): m.end() + 8]
        hm = re.search(f"[{cs._STEM_HANJA}]", win)
        if hm and hm.group(0) not in stems:
            return [("일간", hm.group(0), "·".join(sorted(stems)))]
    return []


# ── 다양한 명식 ──────────────────────────────────────────────
def _bi(y, mo, d, hh=None, mm=0, *, female=False, lunar=False):
    return BirthInput(
        birth_date=date(y, mo, d),
        birth_time=(time(hh, mm) if hh is not None else None),
        calendar=(CalendarType.LUNAR if lunar else CalendarType.SOLAR),
        gender=(Gender.FEMALE if female else Gender.MALE),
        apply_true_solar_time=False,
    )

CHARTS = {
    "A": _bi(1990, 3, 15, 8, 30),
    "B": _bi(1985, 7, 22, 23, 30, female=True),   # 야자시 경계
    "C": _bi(2001, 11, 9),                         # 시미상
    "D": _bi(1978, 5, 3, 14, 0, female=True),
    "E": _bi(1995, 9, 27, 6, 15),
    "F": _bi(1969, 12, 31, 19, 45, female=True, lunar=True),
}


# ── 파이프라인 실행(메뉴 공통) ───────────────────────────────
class Args:
    fast = False
    no_rag = False
    adversarial = False


# 적대적 질문 — '메뉴를 벗어난 명식/일간/세운' 직접 질의. 전체 명식이 context에 없으면 환각 유발.
_ADV_Q = {
    "사주": ["내 사주 명식의 년주·월주·일주·시주를 정확히 알려줘", "내 일간(日干)이 무엇인가요?",
             "올해 내 세운 간지가 뭐예요?"],
    "궁합": ["두 사람 각자의 일간(日干)을 알려줘", "사람A의 일지와 사람B의 일지를 말해줘",
             "두 사람 각자 올해 세운 간지는?"],
    "택일": ["내 사주 일간과 일지가 뭐예요?", "내 명식 4주(년월일시주)를 알려줘", "올해 내 세운 간지가 뭔가요?"],
    "작명": ["내 사주 명식 4주를 정확히 알려줘", "내 일간이 무엇인가요?", "올해 내 세운 간지는?"],
    "개명": ["내 사주 명식 4주를 정확히 알려줘", "내 일간이 무엇인가요?", "올해 내 세운 간지는?"],
    "아호": ["내 사주 명식 4주를 정확히 알려줘", "내 일간이 무엇인가요?", "올해 내 세운 간지는?"],
}


def _adv_plan(menu):
    """(display, message) 리스트 — 모두 followup 형태(message 있음)."""
    return [(q, q) for q in _ADV_Q[menu]]


def _rag(query, question):
    if Args.no_rag:
        return [], None
    ch = cs.retrieve_for_menu(query, "basic", session_id=None, question=question)
    return ch, cs.rag_context_block(ch)


def _gen(sys_content, msgs, *, question, evidence, rag_ctx, saju_summary=None):
    """exaone 1차 → (옵션)qwen 보강. production stream과 동일 입력."""
    draft = cs._call_ollama(msgs)
    if Args.fast or not draft.strip():
        return draft
    qb = cs._refine_with_qwen(question=question, draft=draft, saju_summary=saju_summary,
                              evidence=evidence, rag_context=rag_ctx, dialect_instruction=None)
    return (qb.strip() if qb else draft)


def _measure(answer, *, allow, exclude_date_ctx, stems):
    return {
        "branch": cs._verify_branches(answer, allow, exclude_date_ctx=exclude_date_ctx),
        "stem": _verify_stem_multi(answer, stems),
        "sewoon": _verify_sewoon(answer),
    }


def _run(label, menu, sys_content, msgs, *, brief, allow, stems, question,
         rag_ctx, exclude_date_ctx, truth, saju_summary_for_regen, correct_chart_json, correct_day_stems):
    """1회 실행 → init/final 측정 dict 반환. production 메뉴별 교정 로직을 그대로 미러링.

    사주/tool=단일 chart_json(일간), 궁합=day_stems(두 사람 일간 union). 지지는 모든 메뉴.
    """
    ans0 = _gen(sys_content, msgs, question=question, evidence=brief,
                rag_ctx=rag_ctx, saju_summary=saju_summary_for_regen)
    init = _measure(ans0, allow=allow, exclude_date_ctx=exclude_date_ctx, stems=stems)

    ans = ans0
    _branch = cs._verify_branches(ans0, allow, exclude_date_ctx=exclude_date_ctx)
    _stem = (cs._verify_day_stem(ans0, correct_chart_json) if correct_chart_json else []) \
        + (cs._verify_day_stem_multi(ans0, correct_day_stems) if correct_day_stems else [])
    if _branch or _stem:
        ans = cs._correct_branches(
            ans0, allowed=allow, truth=truth, question=question, sys_content=sys_content,
            saju_summary=saju_summary_for_regen, exclude_date_ctx=exclude_date_ctx,
            chart_json=correct_chart_json, day_stems=correct_day_stems,
        )
    ans = cs._scrub_source_refs(ans)
    final = _measure(ans, allow=allow, exclude_date_ctx=exclude_date_ctx, stems=stems)
    return init, final, ans


def _ok(m):  # 한 측정의 전부 일치 여부
    return not (m["branch"] or m["stem"] or m["sewoon"])


def _fmt(m):
    bits = []
    bits.append("지지" + ("✓" if not m["branch"] else f"✗{m['branch']}"))
    bits.append("일간" + ("✓" if not m["stem"] else f"✗{m['stem']}"))
    bits.append("세운" + ("✓" if not m["sewoon"] else f"✗{m['sewoon']}"))
    return " ".join(bits)


# ── 메뉴별 케이스 ────────────────────────────────────────────
def cases_saju(base_prompt):
    ci = CHARTS["A"]; ch = build_chart(ci); cj = ch.model_dump(mode="json")
    summary = cs._build_saju_summary(ch, ci)
    sysc = cs._compose_sys_content(base_prompt, "standard", "normal")
    truth = cs._myeongsik_truth(cj); stems = {cj["pillars"]["day"]["stem"]}
    _qs = (_ADV_Q["사주"] if Args.adversarial else
           ["성격과 직업운을 알려줘", "올해 전반적인 운세는?", "2026년 9월 15일 시험 합격운 봐줘"])
    for q in _qs:
        chunks, rag_ctx = _rag(q, q)
        msgs = [{"role": "system", "content": sysc},
                {"role": "user", "content": cs._build_user_prompt(q, chunks, summary)}]
        yield ("사주", f"A/{ch.pillars.day.stem}{ch.pillars.day.branch}", q, dict(
            menu="사주", sys_content=sysc, msgs=msgs, brief=summary, allow=cs._allowed_from_charts(cj),
            stems=stems, question=q, rag_ctx=rag_ctx, exclude_date_ctx=False, truth=truth,
            saju_summary_for_regen=summary, correct_chart_json=cj, correct_day_stems=None))


def cases_compat(_):
    a = build_chart(CHARTS["A"]); b = build_chart(CHARTS["B"])
    ca, cb = a.model_dump(mode="json"), b.model_dump(mode="json")
    sa, sb = cs._build_saju_summary(a), cs._build_saju_summary(b)
    result = cmp.compute_compatibility(a, b)
    la, lb = "사람A", "사람B"
    brief = cmp._render_result_for_llm(result, la, lb, sa, sb)
    allow = cs._allowed_from_charts(ca, cb)
    stems = {ca["pillars"]["day"]["stem"], cb["pillars"]["day"]["stem"]}
    truth = cs._charts_truth([(la, ca), (lb, cb)])
    base_sys = cs._compose_sys_content(cmp.COMPAT_SYSTEM, "standard", "normal")
    fu_sys = cs._compose_sys_content(cmp.COMPAT_SYSTEM + cmp.COMPAT_FOLLOWUP_HINT, "standard", "normal")
    _ss = f"{sa}\n\n{sb}"
    plan = ([(q, fu_sys, q) for q in _ADV_Q["궁합"]] if Args.adversarial else
            [("해설", base_sys, None), ("올해 두 사람 관계 흐름은?", fu_sys, "올해 두 사람 관계 흐름은?"),
             ("내년에 결혼하면 좋을까?", fu_sys, "내년에 결혼하면 좋을까?")])
    for disp, sysc, msg in plan:
        q = msg or f"{la}와 {lb} 궁합 해설"
        chunks, rag_ctx = _rag((msg + "\n" + brief) if msg else brief, msg)
        if msg is None:
            uc = brief if not rag_ctx else f"{brief}\n\n[참고자료]\n{rag_ctx}"
            msgs = [{"role": "system", "content": sysc}, {"role": "user", "content": uc}]
        else:
            analysis = f"[궁합 분석]\n{brief}" + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
            _aux = cs._aux_ganji_blocks(msg, include_summary=False)  # 서비스 미러: 세운/날짜 주입
            if _aux:
                analysis = f"{analysis}\n\n{_aux}"
            msgs = [{"role": "system", "content": sysc}, {"role": "user", "content": analysis},
                    {"role": "user", "content": msg}]
        yield ("궁합", "A×B", disp, dict(
            menu="궁합", sys_content=sysc, msgs=msgs, brief=brief, allow=allow, stems=stems,
            question=q, rag_ctx=rag_ctx, exclude_date_ctx=False, truth=truth,
            saju_summary_for_regen=_ss, correct_chart_json=None, correct_day_stems=stems))


def _tool_row(tool, kind, result_json, cj):
    r = ToolSession(tool=tool, kind=kind)
    r.result_json = result_json; r.chart_json = cj
    return r


def cases_taekil(_):
    ci = CHARTS["C"]; ch = build_chart(ci); cj = ch.model_dump(mode="json")
    res = taekil_engine.recommend_dates(ch, date(2026, 6, 20), days=60, purpose="general", top=10)
    row = _tool_row("taekil", None, res.model_dump(mode="json"), cj)
    brief = ts._render(row); sysc = cs._compose_sys_content(ts._system_for(row), "standard", "normal")
    allow = cs._allowed_from_charts(cj); stems = {cj["pillars"]["day"]["stem"]}; truth = cs._myeongsik_truth(cj)
    plan = (_adv_plan("택일") if Args.adversarial else
            [("해설", None), ("추천일 중 최고의 날과 이유는?", "추천일 중 최고의 날과 이유는?"),
             ("올해 안에 이사하기 좋은 날은?", "올해 안에 이사하기 좋은 날은?")])
    for disp, msg in plan:
        q = msg or "택일 해설"
        chunks, rag_ctx = _rag((msg + "\n" + brief) if msg else brief, msg)
        if msg is None:
            uc = brief if not rag_ctx else f"{brief}\n\n[참고자료]\n{rag_ctx}"
            msgs = [{"role": "system", "content": sysc}, {"role": "user", "content": uc}]
        else:
            analysis = f"[분석]\n{brief}" + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
            _aux = cs._aux_ganji_blocks(msg, cj, include_summary=True)  # 서비스 미러: 명식+세운 주입
            if _aux:
                analysis = f"{analysis}\n\n{_aux}"
            msgs = [{"role": "system", "content": sysc}, {"role": "user", "content": analysis},
                    {"role": "user", "content": msg}]
        yield ("택일", f"C/{ch.pillars.day.stem}{ch.pillars.day.branch}", disp, dict(
            menu="택일", sys_content=sysc, msgs=msgs, brief=brief, allow=allow, stems=stems,
            question=q, rag_ctx=rag_ctx, exclude_date_ctx=True, truth=truth,
            saju_summary_for_regen=brief, correct_chart_json=cj, correct_day_stems=None))


def _naming_case(menu_ko, kind, ci_key, surname, given):
    ci = CHARTS[ci_key]; ch = build_chart(ci); cj = ch.model_dump(mode="json")
    if kind == "gaemyeong":
        analysis = naming_engine.analyze_name(surname, given, ch)
        result = {"kind": kind, "analysis": analysis.model_dump(mode="json"),
                  "deficient": naming_engine._deficient_elements(ch)}
        probe = "지금 이름의 약점과 개명하면 뭐가 좋아지나요?"
    else:
        cands = naming_engine.recommend_names(surname, ch, top=40, gender=str(ci.gender))
        result = {"kind": kind, "surname": surname,
                  "candidates": [c.model_dump(mode="json") for c in cands],
                  "deficient": naming_engine._deficient_elements(ch)}
        probe = ("추천한 이름의 한자 뜻과 오행을 설명해줘" if kind == "jakmyeong"
                 else "이 아호의 뜻과 어울리는 이유는?")
    row = _tool_row("naming", kind, result, cj)
    brief = ts._render(row); sysc = cs._compose_sys_content(ts._system_for(row), "standard", "normal")
    allow = cs._allowed_from_charts(cj); stems = {cj["pillars"]["day"]["stem"]}; truth = cs._myeongsik_truth(cj)
    _plan = _adv_plan(menu_ko) if Args.adversarial else [("해설", None), (probe, probe)]
    for disp, msg in _plan:
        q = msg or f"{menu_ko} 해설"
        chunks, rag_ctx = _rag((msg + "\n" + brief) if msg else brief, msg)
        if msg is None:
            uc = brief if not rag_ctx else f"{brief}\n\n[참고자료]\n{rag_ctx}"
            msgs = [{"role": "system", "content": sysc}, {"role": "user", "content": uc}]
        else:
            analysis = f"[분석]\n{brief}" + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
            _aux = cs._aux_ganji_blocks(msg, cj, include_summary=True)  # 서비스 미러: 명식+세운 주입
            if _aux:
                analysis = f"{analysis}\n\n{_aux}"
            msgs = [{"role": "system", "content": sysc}, {"role": "user", "content": analysis},
                    {"role": "user", "content": msg}]
        yield (menu_ko, f"{ci_key}/{ch.pillars.day.stem}{ch.pillars.day.branch}", disp, dict(
            menu=menu_ko, sys_content=sysc, msgs=msgs, brief=brief, allow=allow, stems=stems,
            question=q, rag_ctx=rag_ctx, exclude_date_ctx=False, truth=truth,
            saju_summary_for_regen=brief, correct_chart_json=cj, correct_day_stems=None))


def cases_naming(_):
    yield from _naming_case("작명", "jakmyeong", "D", "金", None)
def cases_gaemyeong(_):
    yield from _naming_case("개명", "gaemyeong", "E", "金", "敏洙")
def cases_aho(_):
    yield from _naming_case("아호", "aho", "F", "", None)


MENU_FNS = {"사주": cases_saju, "궁합": cases_compat, "택일": cases_taekil,
            "작명": cases_naming, "개명": cases_gaemyeong, "아호": cases_aho}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="qwen 보강 생략(빠른 점검)")
    ap.add_argument("--no-rag", action="store_true", help="RAG 생략")
    ap.add_argument("--only", default="", help="메뉴 콤마구분(예: 사주,궁합)")
    ap.add_argument("--adversarial", action="store_true", help="메뉴이탈 명식/일간/세운 직접질의")
    a = ap.parse_args()
    Args.fast = a.fast; Args.no_rag = a.no_rag; Args.adversarial = a.adversarial

    db = get_session_factory()()
    base_prompt = template_service.get_active_prompt(db)
    db.close()

    only = [m.strip() for m in a.only.split(",") if m.strip()] or list(MENU_FNS)
    print(f"세운 기준(올해)={_SEWOON} · qwen={'OFF' if Args.fast else 'ON'} · RAG={'OFF' if Args.no_rag else 'ON'}\n")

    per_menu: dict[str, list] = {}
    for menu in only:
        gen = MENU_FNS[menu](base_prompt)
        for (mname, clabel, disp, kw) in gen:
            try:
                init, final, _ans = _run(clabel, **kw)
            except Exception as e:  # noqa: BLE001
                print(f"  [ERR] {mname} {clabel} {disp}: {type(e).__name__}: {e}")
                per_menu.setdefault(mname, []).append((clabel, disp, False, False, "ERR"))
                continue
            ok_i, ok_f = _ok(init), _ok(final)
            mark = "OK " if ok_i else ("→교정OK" if ok_f else "✗미해결")
            print(f"  [{mark:7}] {mname:3} {clabel:10} | {disp[:22]:22} | final: {_fmt(final)}")
            per_menu.setdefault(mname, []).append((clabel, disp, ok_i, ok_f, _fmt(final)))

    print("\n===== 메뉴별 명식 정합성 =====")
    grand_fail = 0
    for menu in only:
        rows = per_menu.get(menu, [])
        n = len(rows); fi = sum(1 for r in rows if r[2]); ff = sum(1 for r in rows if r[3])
        fails = [r for r in rows if not r[3]]
        grand_fail += len(fails)
        print(f"  {menu}: init {fi}/{n} · final {ff}/{n}" + ("  ✅" if not fails else f"  ❌ 미해결 {len(fails)}"))
        for r in fails:
            print(f"      - {r[1]}: {r[4]}")
    print("\n" + ("ALL_MENUS_CONSISTENT" if grand_fail == 0 else f"FAILS={grand_fail}"))
    return 0 if grand_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
