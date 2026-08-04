"""스트림 과금 보상 불변식 — '생성 전 확정 차감'의 짝인 '실패 시 보상'이 빠짐없이 도는가.

[계기 2026-07-23 감사]
이 서비스는 free-ride 차단을 위해 답변 생성 '전'에 차감/선점을 확정 커밋한다(끝에서 커밋하면
클라 이탈 시 롤백돼 무한 무료가 된다). 그 대가로 **실패하면 반드시 보상**해야 하는데,
내부가 방어한 분기(RAG/LLM 장애·빈 답변·저장 실패) **밖**에서 예외가 나면 API 계층의 포괄 except 가
그대로 삼켜 error 만 내보내고 보상하지 않았다 — 답변 없이 포인트·무료슬롯만 사라졌다.

→ 서비스 진입점을 래퍼로 감싸 receipt(미정산 청구)가 남아 있으면 보상하도록 바꿨다.
이 테스트가 지키는 것은 세 가지다:
  ① 방어 분기 밖 예외 → 보상된다
  ② 내부가 이미 보상한 경우 → **이중환불하지 않는다**(이쪽이 더 위험하다: 공짜 포인트 발급)
  ③ 클라 이탈(GeneratorExit) → 보상하지 않는다(free-ride 차단 규약 유지)

⚠️ 이 테스트를 지우지 말 것. ②를 깨면 사용자가 질문을 반복해 포인트를 무한 증식할 수 있다.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

SVC = pathlib.Path(__file__).resolve().parents[1] / "app" / "services"


def _src(name: str) -> str:
    return io.open(SVC / name, encoding="utf-8").read()


# ── 구조 불변식 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "fname,wrapper,inner",
    [
        ("tool_service.py", "def stream_message(", "def _stream_message_inner("),
        ("chat_service.py", "def post_message_stream(", "def _post_message_stream_inner("),
    ],
)
def test_stream_entrypoint_is_wrapped(fname: str, wrapper: str, inner: str) -> None:
    """공개 진입점은 반드시 보상 래퍼여야 한다(내부 제너레이터를 직접 노출하면 보상이 사라진다)."""
    s = _src(fname)
    assert wrapper in s and inner in s, f"{fname}: 보상 래퍼/내부 제너레이터 구조가 사라졌습니다"
    head = s[s.index(wrapper): s.index(inner)]
    assert "except GeneratorExit" in head, (
        f"{fname}: 래퍼가 GeneratorExit 를 따로 잡지 않습니다 — 클라 이탈이 '실패'로 처리되면 "
        "이탈만으로 환불받는 free-ride 가 열립니다"
    )
    assert "raise" in head, f"{fname}: GeneratorExit 를 re-raise 하지 않습니다"
    assert "_receipt=receipt" in head, f"{fname}: 내부에 receipt 를 넘기지 않습니다(보상 대상 식별 불가)"


@pytest.mark.parametrize(
    "fname,refund_call",
    [
        ("tool_service.py", "chat_service.refund_followup(db, user, bill, _pre_charged"),
        ("chat_service.py", "_refund_free_claim(db, user, bill)"),
    ],
)
def test_every_self_refund_clears_receipt(fname: str, refund_call: str) -> None:
    """내부가 스스로 보상한 자리마다 receipt 를 비워야 한다 — 안 그러면 래퍼가 한 번 더 환불한다.

    이중환불은 '공짜 포인트'라 원래 버그보다 위험하다. 새 보상 분기를 추가할 때 이 테스트가 깨지면
    바로 다음 줄에 `if _receipt is not None: _receipt.clear()` 를 넣어야 한다.
    """
    lines = _src(fname).split("\n")
    # 래퍼 자신의 보상 호출은 제외한다(래퍼는 receipt 를 비울 필요가 없다).
    inner_start = next(i for i, ln in enumerate(lines) if ln.startswith("def _") and "_inner(" in ln)
    bad: list[str] = []
    for i, ln in enumerate(lines):
        if i < inner_start or refund_call not in ln:
            continue
        window = "\n".join(lines[i: i + 4])          # 호출 직후 몇 줄 안에 clear 가 있어야 한다
        if "_receipt.clear()" not in window:
            bad.append(f"{fname}:{i + 1}: {ln.strip()}")
    assert not bad, (
        "내부 보상 직후 receipt 를 비우지 않는 곳이 있습니다(래퍼가 이중환불 → 공짜 포인트):\n  "
        + "\n  ".join(bad)
    )


def test_api_layer_does_not_swallow_without_service_wrapper() -> None:
    """API 포괄 except 가 서비스 보상을 대신하지 않는다는 전제를 명시적으로 고정.

    보상 책임은 서비스(래퍼)에 있다. API 는 메시지만 변환한다. 만약 누군가 서비스 래퍼를 걷어내고
    API 에서 환불하도록 되돌리면, bill/_pre_charged 가 API 스코프에 없어 조용히 미보상으로 회귀한다.
    """
    api = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
    for fname in ("chat.py", "tools.py"):
        s = io.open(api / fname, encoding="utf-8").read()
        assert "refund_followup" not in s and "_refund_free_claim" not in s, (
            f"api/{fname} 에서 직접 환불하고 있습니다 — 보상은 서비스 래퍼 책임입니다"
            "(API 스코프엔 bill/_pre_charged 가 없어 부분 보상만 되고 나머지는 새는 구조가 됩니다)"
        )


# ── 과금 판정 불변식(플러스 패스 무료 5회 오소진) ────────────────────────────
def test_pass_free_basic_respects_allow_free_quota() -> None:
    """플러스 월 무료 기본질문은 allow_free_quota=False 경로에서 소진되면 안 된다.

    [버그 2026-07-23] 이 조건이 빠져 있어, '입장료를 냈으니 추가질문은 항상 차감'이어야 할
    프리미엄·툴 계열 추가질문이 플러스의 월 무료 5회를 대신 태웠다(같은 함수 docstring 계약 위반).
    """
    s = _src("chat_service.py")
    m = re.search(r'free_q = settings_service\.get_int\(db, "pass_free_basic_monthly".*?\n(.*?)\n', s, re.S)
    assert m, "패스 무료 기본질문 판정 블록을 찾지 못했습니다"
    guard = re.search(r'if allow_free_quota and depth == "basic" and free_q > 0:', s)
    assert guard, (
        "패스 무료 기본질문 조건에 allow_free_quota 가 없습니다 — 프리미엄 추가질문이 "
        "플러스 월 무료 5회를 소진시킵니다"
    )


def test_followup_billing_ui_does_not_promise_free() -> None:
    """추가질문 과금바는 '무료'를 약속하면 안 된다(서버가 allow_free_quota=False 로 항상 차감).

    [버그 2026-07-23] free_remaining>0 이면 "이번 질문 무료 👍" 라고 띄웠는데 실제로는 1,900P 가
    빠졌다. 이 컴포넌트가 붙는 화면(궁합·툴 전 메뉴 추가질문)은 전부 무료한도 미적용 경로다.
    """
    fe = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "FollowupBilling.tsx"
    if not fe.is_file():
        pytest.skip("frontend 소스 없음")
    s = fe.read_text(encoding="utf-8")
    # 주석은 제외하고 '실행되는 코드'만 본다 — 블록주석(/** */)에 버그 경위를 적어 두므로
    # 그것까지 잡으면 설명을 남길 수 없다(첫 작성 때 실제로 자기 주석에 걸렸다).
    code = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    code = "\n".join(ln.split("//", 1)[0] for ln in code.split("\n"))
    assert "free_remaining" not in code, (
        "FollowupBilling 이 free_remaining 을 다시 참조합니다 — 이 화면의 과금과 무관한 값이라 "
        "'무료' 오안내가 재발합니다"
    )
    assert "이번 질문 무료" not in code, "추가질문 과금바가 '무료'를 약속하고 있습니다(서버는 차감)"
