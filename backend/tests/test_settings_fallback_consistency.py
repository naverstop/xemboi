"""설정 폴백 기본값 == DEFAULTS 불변식 (돈 사고 재발 방지).

[계기 2026-07-22] settings_service.get_int(db, "amulet_cost_p", 3000) 처럼 호출부 폴백이
DEFAULTS("3900")와 달랐다. DB 행이 유실되거나 조회에 실패하면 3,900P 상품이 3,000P 에 팔려
건당 900P 를 회사가 손실한다. 게다가 표시(me 응답)도 같은 폴백을 써서 사용자는 눈치채지 못한다.

기계적으로 전 소스를 훑어 '숫자 폴백'이 DEFAULTS 와 다른 곳을 잡는다.
새 설정을 추가하거나 기본값을 바꿀 때 이 테스트가 깨지면 호출부 폴백도 함께 고쳐야 한다.

⚠️ 이 테스트를 지우지 말 것 — 실측으로만 발견되던 유형이라 사람이 놓치기 쉽다.
"""
from __future__ import annotations

import io
import pathlib
import re

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"
SETTINGS_PY = APP_DIR / "services" / "settings_service.py"

# 금액이 아닌 값(재생시간 등)이라 호출부가 의도적으로 다른 상한을 쓰는 경우만 예외로 둔다.
# 돈 관련 키는 절대 여기에 넣지 말 것.
ALLOWED_MISMATCH = {
    "shorts_video_seconds",
    "shorts_video_seconds_max",
}

_CALL_RE = re.compile(
    r"""get_(?:int|str|bool)\(\s*db\s*,\s*["']([a-z_]+)["']\s*,\s*([^),]+)\)"""
)


def _defaults() -> dict[str, str]:
    src = io.open(SETTINGS_PY, encoding="utf-8").read()
    block = re.search(r"DEFAULTS[^=]*=\s*\{(.*?)\n\}", src, re.S)
    assert block, "settings_service.DEFAULTS 블록을 찾지 못했습니다"
    return dict(re.findall(r'"([a-z_]+)"\s*:\s*"([^"]*)"', block.group(1)))


def test_setting_fallbacks_match_defaults() -> None:
    defaults = _defaults()
    assert defaults, "DEFAULTS 파싱 실패"

    bad: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        if path.name == "settings_service.py":
            continue
        text = io.open(path, encoding="utf-8").read()
        for key, raw in _CALL_RE.findall(text):
            fb = raw.strip().strip("\"'")
            if key not in defaults or key in ALLOWED_MISMATCH:
                continue
            # 숫자 폴백만 비교(변수·표현식 폴백은 정적으로 판정 불가)
            if not fb.lstrip("-").isdigit() or not defaults[key].lstrip("-").isdigit():
                continue
            if fb != defaults[key]:
                rel = path.relative_to(APP_DIR.parent.parent)
                bad.append(f"{rel}: {key} 폴백={fb} vs DEFAULTS={defaults[key]}")

    assert not bad, (
        "설정 폴백이 DEFAULTS 와 다릅니다(DB 행 유실 시 잘못된 금액이 적용됨):\n  "
        + "\n  ".join(sorted(bad))
    )
