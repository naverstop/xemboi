# -*- coding: utf-8 -*-
"""품질게이트 강화 — 판독불가 OCR 차단 (2026-07 전수진단 후속).

실측: PDF 코퍼스의 63%가 내용파괴 의심인데 종전 게이트(한글비율)는 '오인식된 한글'을
통과시켰다. 라틴 난수열·기호 연속·단어 파편(줄당 평균 글자수) 지표를 추가했다.
"""
from __future__ import annotations

from ml.data_pipeline.tagging import is_low_quality

_NL = "\n"


def test_blocks_word_salad_ocr():
    # PaddleOCR 스캔 오인식 — 줄당 3~5자 단어 파편(실측 '司人가⏎오면⏎촛水로')
    t = _NL.join(["個水이", "비를", "맞아", "좋지만", "司人가", "오면", "촛水로",
                  "인하여", "四人를", "볼수", "없으므로", "없다"])
    assert is_low_quality(t)


def test_blocks_latin_gibberish_and_symbol_runs():
    base = "민라닥이서 가라는 관리치는커이라 관리종목이 는것이다 오른다 것이 관리종극 진행장라"
    assert is_low_quality(base + " PPpopeerpopopeprpepgpepepop")     # 라틴 난수열
    assert is_low_quality(base + " ++++$++++$+$++")                   # 기호 연속


def test_passes_normal_texts():
    # 띄어쓰기 없는 정상 추출본(명리전 2권 유형)
    assert not is_low_quality(
        "乙木이戊土위에서피어난다는" + _NL + "것은, 단지환경에적응하는것을넘어서, 그환경을"
        + _NL + "자기만의세계로전환할줄아는지혜와고상한품격을지녔다는것을의미한다."
    )
    # 유튜브 자막(문장 단위 줄)
    assert not is_low_quality(_NL.join([
        "상가집 갔다 왔을 때 조심해야 돼요.", "상가집 가지 말아야 돼요.", "그렇지.",
        "잘못 가면 이런 아이들은 왜냐하면 이 아이가 지금 극신약이잖아요.",
        "우리가 극신약사주 들어서 상가집 잘못 가면 진짜 상몽 들어요.",
    ]))
    # 영단어 한두 개는 통과(오탐 방지)
    assert not is_low_quality(
        "계약은천간에재성(식상)과인성이合되면서일지와剋이되지않으면계약된다고 설명했다. "
        "OK? communication 같은 영단어 하나는 저품질이 아니다. 이후로도 문장이 이어진다."
    )
