# -*- coding: utf-8 -*-
"""신년운세 월별 풍부화 — 결정적 사실 주입 검증 (2026-07-16 운영자 지시).

원칙: 월별 해설을 풍부하게 하되 환각은 철저 방지 → LLM에게 '길게 써라'가 아니라
결정적 재료(월지 십성·월운↔내 사주 합충형파·궁위)를 엔진으로 계산해 준다.
관계 계산은 gwanbeop._pair_relations(감수된 관법 엔진) 재사용 — 새 테이블 작성 금지.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.app.saju.constants import compute_ten_god
from backend.app.saju.engine import build_chart
from backend.app.saju.pillars import compute_pillars
from backend.app.saju.types import BirthInput, CalendarType, Gender
from backend.app.services import tool_service as T


def _chart():
    return build_chart(BirthInput(birth_date=date(2006, 8, 10), calendar=CalendarType.SOLAR,
                                  gender=Gender.FEMALE))


def test_branch_ten_god_uses_main_hidden_stem():
    """월지 십성 = 지장간 정기 기준(관법 엔진과 동일 용법)."""
    # 丑 정기=己 → 辛 일간에 편인(偏印)
    assert T._branch_ten_god("辛", "丑") == "偏印"
    # 寅 정기=甲 → 辛 일간에 정재(正財)
    assert T._branch_ten_god("辛", "寅") == "正財"
    assert T._branch_ten_god("辛", "없는글자") == ""  # 실패 시 빈 문자열(크래시 금지)


def test_month_relations_match_classic_tables():
    """월운↔내 4주 관계가 고전 테이블과 일치(축미충·인신충형·묘술합·진술충)."""
    ch = _chart()  # 지지: 년戌 월申 일未
    def rels_of(month: int) -> str:
        fp = compute_pillars(BirthInput(birth_date=date(2027, month, 15)))[0]
        return " / ".join(T._month_natal_relations(ch, fp.month.stem, fp.month.branch))
    r1 = rels_of(1)   # 丑월
    assert "미(未) 충" in r1 and "배우자·가정궁" in r1     # 축미충 → 일지(배우자궁)
    assert "술(戌) 형" in r1                               # 축술형
    r2 = rels_of(2)   # 寅월
    assert "신(申) 충" in r2 and "사회·직장궁" in r2       # 인신충 → 월지(직장궁)
    r3 = rels_of(3)   # 卯월
    assert "술(戌) 합" in r3                               # 묘술 육합
    r4 = rels_of(4)   # 辰월
    assert "술(戌) 충" in r4                               # 진술충


def test_month_relations_empty_for_calm_month():
    """관계 없는 달은 빈 리스트(없는 합충을 만들지 않음 — 환각 방지의 핵심).

    Phase 2 확장(반합·원진·해) 반영: 종전 '무난'이던 12월(子)은 자미 원진·해가 실재해 제외,
    진짜 무난한 8월(申월 — 같은 글자 申은 자형 아님·반합 가드)로 교체."""
    ch = _chart()  # 지지: 년戌 월申 일未
    fp = compute_pillars(BirthInput(birth_date=date(2027, 8, 15)))[0]  # 申월
    assert T._month_natal_relations(ch, fp.month.stem, fp.month.branch) == []


def test_extended_relations_detected():
    """Phase 2 확장 관계(원진·해)도 결정적으로 검출 — 12월(子) vs 일지 未 = 원진·해(고전 육해)."""
    ch = _chart()
    fp = compute_pillars(BirthInput(birth_date=date(2027, 12, 15)))[0]  # 子월
    rels = " / ".join(T._month_natal_relations(ch, fp.month.stem, fp.month.branch))
    assert "원진" in rels and "해" in rels and "배우자·가정궁" in rels


def test_create_months_carry_new_facts():
    """create_sinnyeon 이 만드는 월 항목에 새 결정적 필드가 실린다(스키마 회귀 방지)."""
    ch = _chart()
    day_stem = ch.pillars.day.stem
    fp = compute_pillars(BirthInput(birth_date=date(2027, 1, 15)))[0]
    m = {
        "month": 1, "label": "x", "stem": fp.month.stem, "branch": fp.month.branch,
        "ten_god": compute_ten_god(day_stem, fp.month.stem),
        "branch_ten_god": T._branch_ten_god(day_stem, fp.month.branch),
        "relations": T._month_natal_relations(ch, fp.month.stem, fp.month.branch),
    }
    assert m["branch_ten_god"] and isinstance(m["relations"], list) and m["relations"]


def test_render_includes_relations_and_no_hallucination_guard():
    """_render 근거에 월지 십성·관계가 실리고, 환각 금지·달별 분량 지시가 포함된다."""
    ch = _chart()
    day_stem = ch.pillars.day.stem
    months = []
    for m in range(1, 13):
        fp = compute_pillars(BirthInput(birth_date=date(2027, m, 15)))[0]
        months.append({
            "month": m, "label": f"{fp.month.stem}{fp.month.branch}",
            "stem": fp.month.stem, "branch": fp.month.branch,
            "ten_god": compute_ten_god(day_stem, fp.month.stem),
            "branch_ten_god": T._branch_ten_god(day_stem, fp.month.branch),
            "relations": T._month_natal_relations(ch, fp.month.stem, fp.month.branch),
        })
    row = SimpleNamespace(tool="sinnyeon", kind=None, input_json={"year": 2027},
                          result_json={"year": 2027, "seun": {}, "day_stem": day_stem,
                                       "day_strength": ch.day_master_strength,
                                       "domains": [], "months": months})
    out = T._render(row)
    assert "월지 십성" in out and "배우자·가정 자리" in out   # 궁위 라벨을 쉬운 말로
    assert "특별한 관계 없음(무난)" in out               # 평온한 달 명시(합충 창작 차단)
    assert "지어내지 마세요" in out and "달마다 다른" in out   # 환각 금지 + 밀도형(달별 고유 재료)
    # 시스템 프롬프트도 동일 원칙
    assert "환각 금지" in T.SINNYEON_SYSTEM and "3,500~4,500자" in T.SINNYEON_SYSTEM


def test_relations_are_deterministic():
    """같은 입력 → 항상 같은 관계 목록(순서 포함) — 재현성."""
    ch = _chart()
    fp = compute_pillars(BirthInput(birth_date=date(2027, 5, 15)))[0]
    a = T._month_natal_relations(ch, fp.month.stem, fp.month.branch)
    b = T._month_natal_relations(ch, fp.month.stem, fp.month.branch)
    assert a == b and a


# ── #10: 간여지동 세운(丙午 등)의 협소함 완화 — 지장간 숨은 십성·십이운성·십이신살 보강 ──
_FAM = {"正官": "官", "偏官": "官", "正印": "印", "偏印": "印", "正財": "財", "偏財": "財",
        "食神": "食", "傷官": "食", "比肩": "比", "劫財": "比"}


def test_seun_depth_lines_enrich_ganyeojidong_year():
    """간여지동 세운(2026 丙午: 천간 丙火 = 지지 午 정기 丁火)은 겉 십성이 한 계열로 좁다.
    지장간 숨은 십성이 '다른 계열'을 공급해 서술 주제를 넓히는지 검증(#10 빈약·단조 방지)."""
    from backend.app.saju.relations import branch_ten_god
    for dm in ("庚", "己"):
        main = {_FAM[compute_ten_god(dm, "丙")], _FAM[branch_ten_god(dm, "午")]}
        assert len(main) == 1, f"{dm}: 丙午 겉 십성은 한 계열이어야(간여지동 전제)"
        lines = T._seun_depth_lines(dm, "午", "寅", True)
        assert lines and "지장간" in lines[0]
        hidden = {_FAM.get(compute_ten_god(dm, st), "?") for st in ("丙", "己", "丁")}
        assert hidden - main, f"{dm}: 지장간이 겉 계열({main}) 밖 새 계열을 도입해 협소를 완화해야"
        assert any("십이운성" in ln for ln in lines) and any("십이신살" in ln for ln in lines)


def test_render_sinnyeon_includes_seun_depth():
    """_render(신년운세) 출력에 세운 지지 지장간·십이운성 심화 근거가 실린다(#10 회귀 방지)."""
    ch = _chart()
    row = SimpleNamespace(
        tool="sinnyeon", kind=None, input_json={"year": 2026}, gender="female",
        chart_json=ch.model_dump(mode="json"),
        result_json={"year": 2026,
                     "seun": {"stem": "丙", "branch": "午", "stem_ko": "병", "branch_ko": "오"},
                     "day_stem": ch.pillars.day.stem, "day_strength": ch.day_master_strength,
                     "domains": [], "months": []})
    out = T._render(row)
    assert "지장간" in out and "십이운성" in out


def test_month_depth_distinct_material():
    """달별 고유 재료(12운성·12신살)가 12달 모두 서로 달라, 브리핑에 실린다(#10 반복 근본해소)."""
    stages = {T._month_depth_line("丁", compute_pillars(
        BirthInput(birth_date=date(2026, m, 15)))[0].month.branch, "卯") for m in range(1, 13)}
    assert len(stages) == 12                     # 12달 재료가 전부 다름
    # _render 브리핑에도 운성·신살이 실림
    ch = _chart(); day_stem = ch.pillars.day.stem
    months = []
    for m in range(1, 13):
        fp = compute_pillars(BirthInput(birth_date=date(2026, m, 15)))[0]
        months.append({"month": m, "label": f"{fp.month.stem}{fp.month.branch}",
                       "stem": fp.month.stem, "branch": fp.month.branch,
                       "ten_god": compute_ten_god(day_stem, fp.month.stem),
                       "branch_ten_god": T._branch_ten_god(day_stem, fp.month.branch),
                       "relations": T._month_natal_relations(ch, fp.month.stem, fp.month.branch)})
    row = SimpleNamespace(tool="sinnyeon", kind="2026", input_json={"year": 2026}, gender="female",
                          chart_json=ch.model_dump(mode="json"),
                          result_json={"year": 2026, "seun": {"stem": "丙", "branch": "午"},
                                       "day_stem": day_stem, "day_strength": ch.day_master_strength,
                                       "domains": [], "months": months})
    out = T._render(row)
    assert out.count("운성 ") >= 12 and out.count("신살 ") >= 12


def test_dedupe_repeated_sentences():
    """여러 달에 복붙된 긴 문장의 2번째 이후만 제거하고, 정상문·라벨은 보존(#10)."""
    from backend.app.services.chat_service import _dedupe_repeated_sentences as dd
    rep = ("• 6월: 오라는 기운이 강합니다. 4~7월 사이에는 정관의 기운이 활성화되어 있어 당신의 진심과 능력은 인정받으며 발전할 가능성이 큽니다.\n"
           "• 9월: 정서가 가라앉습니다. 4~7월 사이에는 정관의 기운이 활성화되어 있어 당신의 진심과 능력은 인정받으며 발전할 가능성이 큽니다.\n"
           "• 12월: 마지막 달입니다.")
    out = dd(rep)
    assert out.count("정관의 기운이 활성화") == 1        # 3→1
    assert "6월" in out and "9월" in out and "12월" in out
    normal = "올해는 좋은 해입니다. 건강을 챙기세요. 재물운이 안정적입니다."
    assert dd(normal) == normal                          # 반복 없으면 불변


def test_fix_sinnyeon_seun_ganji_corrects_and_preserves():
    """세운 간지 환각(병오→갑오 등)은 실제 세운으로 교정하되, 월운·천간단독은 불변(#10)."""
    from backend.app.services.chat_service import _fix_sinnyeon_seun_ganji as fix
    # 교정: 세운/연도 앵커 + 한자병기
    assert fix("올해 세운은 갑오(甲午)로", 2026) == "올해 세운은 병오(丙午)로"
    assert fix("2026년 세운 임오(壬午)가", 2026) == "2026년 세운 병오(丙午)가"
    # 유지: 이미 정답 / 월운 간지 / 천간 단독 / 한자없는 '갑자기'
    assert fix("세운 병오(丙午)의 기운", 2026) == "세운 병오(丙午)의 기운"
    assert fix("9월 정유(丁酉)월은 결실", 2026) == "9월 정유(丁酉)월은 결실"
    assert fix("세운 천간 병(丙)은 편관", 2026) == "세운 천간 병(丙)은 편관"
    assert fix("세운은 갑자기 변동이", 2026) == "세운은 갑자기 변동이"
