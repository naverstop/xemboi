"""작명 엔진 v2 불변식 — 원획법·81수리 격이름·소리오행 名格·소리음양·훈음(2026-07).

이 기능들은 관법 데이터라 리뷰로 회귀를 잡기 어렵다. 핵심 동작을 고정한다.
⚠️ 원획법은 격 결과가 바뀌는 근본 수정 — 되돌릴 땐 이 테스트를 함께 지워야 하므로 의도가 드러난다.
"""
from __future__ import annotations

from backend.app.saju import naming as N


# ── 원획법(原劃法) ──────────────────────────────────────────────────────────
def test_wonhoek_radical_corrections() -> None:
    """변형부수는 원래 부수 획수로 환원(氵→水+1, 王→玉+1, 礻→示+1 등). 원형부수는 보정 안 함."""
    assert N._strokes_wonhoek("珍") == (N._strokes("珍") + 1)   # 王→玉 +1
    assert N._strokes_wonhoek("洙") == (N._strokes("洙") + 1)   # 氵→水 +1
    assert N._strokes_wonhoek("愼") == (N._strokes("愼") + 1)   # 忄→心 +1
    # 원형 부수 글자 자체는 완전형이라 보정하지 않는다(示=5지 6이 아님)
    assert N._strokes_wonhoek("示") == N._strokes("示")
    assert N._strokes_wonhoek("玉") == N._strokes("玉")
    # 원획=옥편인 부수는 불변
    assert N._strokes_wonhoek("宋") == N._strokes("宋")


def test_wonhoek_applied_to_four_pillars() -> None:
    """4격은 옥편이 아니라 원획으로 센다 — 珍(옥편9→원획10)이 반영돼야 한다."""
    fp = N._four_pillars("宋", "珍旿")   # 宋7 珍10(원획) 旿8
    assert fp["won"]["num"] == 18, "원격=珍10+旿8=18 이어야(원획 미적용 시 17)"
    assert fp["jeong"]["num"] == 25, "정격=宋7+珍10+旿8=25 이어야"


def test_number_special_strokes() -> None:
    """숫자 한자는 '뜻하는 수'로(七=7, 十=10). 관법 선택 대상이나 데이터 반영 확인."""
    assert N._strokes_wonhoek("七") == 7
    assert N._strokes_wonhoek("十") == 10


# ── 81수리 격 이름 ──────────────────────────────────────────────────────────
def test_suri_names_loaded() -> None:
    assert N._suri_name(15)["name_ko"] == "통솔격"
    assert N._suri_name(17)["name_ko"] == "건창격"
    assert N._suri_grade(58) == "길"    # 5출처 다수결 정정(엔진이 흉이던 것)
    assert N._suri_grade(49) == "평"    # 논쟁 → 중립


# ── 소리오행 名格 ────────────────────────────────────────────────────────────
def test_sori_ohaeng_namgyeok() -> None:
    """인접 소리오행 상생/상극으로 名格 등급. 상생 순환이면 매우좋음, 상극이면 나쁨."""
    # 김민서 = ㄱ(木)ㅁ(水)ㅅ(金) → 水生木? 木水상생·水金상생 → 매우좋음
    r = N.sori_ohaeng_namgyeok("김민서")
    assert r and r["grade"] == "매우좋음"
    assert r["elements"] == ["목", "수", "금"]
    # 상극 포함이면 나쁨
    bad = N.sori_ohaeng_namgyeok("갈동")   # ㄱ(木)ㄷ(火) 상생... 다른 케이스로
    # 木克土 상극 케이스: 가호 = ㄱ(木)ㅎ(土) → 상극 → 나쁨
    g = N.sori_ohaeng_namgyeok("가호")
    assert g and g["grade"] == "나쁨"


def test_chosung_mapping_matches_namgyeok_research() -> None:
    """名格 리서치 초성치환(술가오행)이 엔진 _CHO_ELEM 과 일치해야(관법 충돌 없음)."""
    assert N._CHO_ELEM["ㅇ"] == "土" and N._CHO_ELEM["ㅁ"] == "水"


# ── 소리음양(모음) ──────────────────────────────────────────────────────────
def test_sori_eumyang_vowels() -> None:
    """모음 음양: ㅏ=양, ㅓ=음, ㅣ=중성(제자원리 채택)."""
    assert N._jungseong_yy("가") == "양"
    assert N._jungseong_yy("거") == "음"
    assert N._jungseong_yy("기") == "중성"
    r = N.sori_eumyang("서연")   # ㅓ(음)ㅕ(음) → 순음 치우침
    assert r and r["grade"] in ("재고", "보통")


# ── 훈음(뜻+음) ─────────────────────────────────────────────────────────────
def test_hun_of() -> None:
    assert N.hun_of("珍") == "보배 진"
    assert N.hun_of("宋").endswith("송")   # '송나라 송' 또는 '성 송'


# ── 한자 picker 필터(벽자·흉자 제외) ────────────────────────────────────────
def test_lookup_by_reading_filters_bad_and_obscure() -> None:
    """picker 는 이름에 쓸 만한 글자만 — 벽자(우거질 진)·흉자(까마귀 오·거만할 오)는 빠지고,
    좋은 인명용 길자(旿 밝을 오)와 상용(珍 보배 진)은 남는다.
    [운영자 지적 2026-07-27] 종전엔 사전 전체 노출로 '숯 많고 검을 진' 같은 글자가 잔뜩 나왔다."""
    jin = {x["char"] for x in N.lookup_by_reading("진", limit=200)}
    assert "珍" in jin and "眞" in jin        # 좋은/상용 글자는 유지
    assert "蓁" not in jin and "侲" not in jin  # 벽자(우거질·아이) 제외
    oh = {x["char"] for x in N.lookup_by_reading("오", limit=200)}
    assert "旿" in jin.__class__(["旿"]) or "旿" in oh   # 밝을 오(좋은 인명용) 유지
    assert "旿" in oh
    assert "烏" not in oh and "傲" not in oh and "誤" not in oh   # 까마귀·거만할·그르칠 제외
