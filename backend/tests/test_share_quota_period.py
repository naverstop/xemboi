"""공유 쿼터 불변식 — '월 N회'가 실제로 월마다 돌아오는가, 그리고 모든 공유 경로가 같은 한도를 쓰는가.

[계기 2026-07-23 실측] 두 건이 동시에 있었다.
  ① 화면은 "공유 월 20회"라고 안내하는데 share_used_count 를 0으로 되돌리는 코드가 없었다.
     라이브 재현: 라이트 패스 20회 소진 → 30일 갱신(3,900P 차감됨) → 공유 잔여 0, 403.
     즉 2개월차부터 돈만 내고 공유 혜택이 없었다.
  ② api/pdf.py 의 메일 공유가 _share_limit 대신 share_quota_default(=5)를 직접 읽어,
     주석의 "record_share 와 동일 규칙"과 달리 패스 확대가 반영되지 않았다.

둘 다 '읽으면 맞아 보이는' 코드라 리뷰로는 안 잡혔고 실측으로만 드러났다.
⚠️ 이 테스트를 지우지 말 것. 특히 test_all_share_paths_use_one_module 은 새 공유 경로가
   또 자기만의 한도 계산을 복제하는 것을 기계적으로 막는다.
"""
from __future__ import annotations

import io
import pathlib
import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
from backend.app.repositories.auth_models import User, UserPass
from backend.app.services import share_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _user(db, uid: int = 900, level: int = 3) -> User:
    u = User(id=uid, email=f"share{uid}@t.test", password_hash="x", level=level,
             share_used_count=0, share_period_start=datetime.utcnow())
    db.add(u)
    db.commit()
    return u


def _give_pass(db, uid: int, tier: str = "lite") -> None:
    now = datetime.utcnow()
    # BigInteger PK 는 sqlite 에서 autoincrement 되지 않으므로 명시 id 부여(운영 PostgreSQL 은 자동).
    db.add(UserPass(id=uid, user_id=uid, tier=tier, started_at=now, current_start=now,
                    next_renewal_at=now + timedelta(days=30), active=True,
                    auto_renew=True, price_p=3900))
    db.commit()


def test_free_user_capped_then_resets_next_period(db):
    """무료회원 5회 소진 → 6회차 차단. 30일이 지나면 자동으로 다시 5회."""
    u = _user(db)
    for _ in range(5):
        share_service.consume(db, u)
    assert share_service.quota_payload(db, u)["remaining"] == 0
    with pytest.raises(share_service.QuotaExceeded):
        share_service.consume(db, u)

    # 주기 앵커를 31일 전으로 되돌린다 = '다음 달'이 온 상황
    u.share_period_start = datetime.utcnow() - timedelta(days=31)
    db.commit()

    q = share_service.quota_payload(db, u)
    assert q["used"] == 0, "30일이 지났는데 사용량이 리셋되지 않았다(과거 '평생 한도' 버그의 재발)"
    assert q["remaining"] == 5
    share_service.consume(db, u)          # 새 주기에서는 다시 공유된다
    assert share_service.quota_payload(db, u)["used"] == 1


def test_pass_holder_gets_expanded_quota_and_it_also_resets(db):
    """패스 이용 시 20회로 확대되고, 그 20회도 매 주기 복구된다(2개월차 0회 방지)."""
    u = _user(db, uid=901)
    _give_pass(db, 901, "lite")
    assert share_service.limit(db, u) == 20

    for _ in range(20):
        share_service.consume(db, u)
    with pytest.raises(share_service.QuotaExceeded):
        share_service.consume(db, u)

    u.share_period_start = datetime.utcnow() - timedelta(days=31)
    db.commit()
    assert share_service.quota_payload(db, u)["remaining"] == 20, \
        "패스 2개월차인데 공유 쿼터가 복구되지 않았다 — 갱신비만 내고 혜택 0인 상태"


def test_plus_tier_also_gets_share_quota(db):
    """플러스는 '라이트 혜택 전체'를 포함하므로 공유 확대도 받아야 한다(tier 로 막히면 안 됨)."""
    u = _user(db, uid=902)
    _give_pass(db, 902, "plus")
    assert share_service.limit(db, u) == 20


def test_refund_returns_one_and_never_goes_negative(db):
    """메일 발송 실패 등으로 환원할 때 1회만 돌려주고 음수로 내려가지 않는다."""
    u = _user(db, uid=903)
    share_service.consume(db, u)
    share_service.refund(db, u)
    assert share_service.quota_payload(db, u)["used"] == 0
    share_service.refund(db, u)           # 이미 0 — 더 내려가면 안 된다
    assert share_service.quota_payload(db, u)["used"] == 0


def test_admin_unlimited_is_not_consumed(db):
    """관리자(level<=1)는 무제한이라 카운터를 소비하지 않는다."""
    u = _user(db, uid=904, level=1)
    for _ in range(30):
        share_service.consume(db, u)
    q = share_service.quota_payload(db, u)
    assert q["unlimited"] is True and q["used"] == 0 and q["remaining"] == -1


# ── 복제 방지(구조 검사) ─────────────────────────────────────────────────────
_API_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"


def test_all_share_paths_use_one_module() -> None:
    """공유 한도를 쓰는 API 가 share_service 밖에서 직접 판정하지 못하게 막는다.

    과거 pdf.py 가 share_quota_default 를 직접 읽어 패스 확대를 놓쳤다. 한도 계산이 다시
    복제되면(=share_used_count 를 직접 UPDATE 하거나 share_quota_default 를 직접 읽으면) 실패시킨다.
    """
    bad: list[str] = []
    for path in _API_DIR.rglob("*.py"):
        text = io.open(path, encoding="utf-8").read()
        if "share_used_count" not in text and "share_quota_default" not in text:
            continue
        # 주석/문서 줄은 제외하고 '실행되는 코드'만 본다.
        for i, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"share_used_count\s*=|values\(share_used_count|share_quota_default", code):
                bad.append(f"{path.name}:{i}: {line.strip()}")
    assert not bad, (
        "공유 한도를 share_service 밖에서 직접 다루는 코드가 있습니다"
        "(패스 확대·주기 리셋이 누락되는 경로가 생깁니다):\n  " + "\n  ".join(bad)
    )


# ── 프론트 공유 규약 가드(구조 검사) ────────────────────────────────────────
# [계기 2026-07-23] 감사에서 프론트 공유 경로에 세 유형이 반복 확인됐다.
#   ① 모바일 네이티브 공유가 '공유 → 집계' 순서라 한도를 못 막음(모바일 사실상 무제한)
#   ② 한도 판정을 한국어 문구 부분일치로 해서, ERR_MAP 카피 한 줄 수정에 전 채널 fail-open
#   ③ 새 공유 화면(SnackPage)이 집계 자체를 빠뜨림
# 전부 '읽으면 맞아 보이는' 코드라 리뷰로 안 잡혔다. 아래는 그 셋을 기계적으로 막는다.
_FRONT_DIR = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"

# 앱 자체를 알리는 공유(서비스 홍보)는 답변 공유 쿼터 대상이 아니다 — 의도적 예외.
_QUOTA_FREE_SHARE = {"ShareFab.tsx", "InstallPrompt.tsx", "appShare.ts"}


def _front_files() -> list[pathlib.Path]:
    if not _FRONT_DIR.is_dir():
        return []
    return [p for p in _FRONT_DIR.rglob("*.ts*") if p.name not in _QUOTA_FREE_SHARE]


def test_front_share_never_judges_quota_by_korean_text() -> None:
    """한도 판정은 ApiError.code 로만 — 한국어 문구 부분일치는 카피 수정에 무증상으로 뚫린다."""
    bad = [
        f"{p.name}:{i}: {ln.strip()}"
        for p in _front_files()
        for i, ln in enumerate(io.open(p, encoding="utf-8").read().splitlines(), 1)
        if 'includes("공유 횟수")' in ln.split("//", 1)[0]
    ]
    assert not bad, (
        "공유 한도를 한국어 문구로 판정하고 있습니다. ERR_MAP 문구를 다듬는 순간 제한이 조용히 "
        "사라집니다(code === \"share_quota_exceeded\") 로 판정하세요:\n  " + "\n  ".join(bad)
    )


def test_front_share_counters_have_precheck() -> None:
    """공유를 집계(submitShare)하는 화면은 사전 확인(shareQuota)도 반드시 갖는다.

    사전 확인이 없으면 '공유가 이미 나간 뒤 403' 이 되어 한도가 강제되지 않는다.
    실제 공유 동작(OS 공유시트·클립보드·카카오 SDK)은 서버가 막을 수 없으므로 이것이 유일한 강제 지점이다.
    """
    bad: list[str] = []
    for p in _front_files():
        text = io.open(p, encoding="utf-8").read()
        if p.name == "api.ts":          # API 정의부는 소비자가 아니다
            continue
        if not re.search(r"\bapi\.submitShare\s*\(", text):
            continue
        # 부분문자열이 아니라 '호출' 형태로 본다 — shareQuotaXX 같은 오타·이름변경이 통과하면 안 된다.
        if not re.search(r"\bapi\.shareQuota\s*\(", text):
            bad.append(str(p.relative_to(_FRONT_DIR)))
    assert not bad, (
        "공유를 집계하면서 사전 한도 확인(api.shareQuota)이 없는 화면이 있습니다 "
        "— 한도 초과여도 공유가 먼저 나갑니다:\n  " + "\n  ".join(bad)
    )
