"""유료 추가질문 영수증(answer_receipts) — 선차감 → 완결(EOF) 추적으로 크래시 orphan 결정적 탐지.

배경: 추가질문(궁합/타로/작명·개명·아호·택일/해몽)은 free-ride 차단을 위해 답변 생성 '전'에 유료를
확정 커밋한다(precharge_followup). 전원차단·강제재기동이 '차감 커밋 ~ 답변 완결' 사이를 때리면
'차감 O · 답변 X' orphan 이 되는데, 차감↔답변 연결키가 세션단위라 원장만으로는 탐지 불가였다.
→ 영수증(receipt)에 per-차감 상태(pending/complete/refunded)를 durable 하게 남겨 결정적으로 판정한다.

수명주기:
  · open_receipt(pending)  : precharge_followup 이 차감과 '동일 트랜잭션'에서 생성(차감과 원자적).
  · finalize_receipt(complete): 각 메뉴 'done'(EOF) 직전 — 답변이 전달·확정됐다는 durable 증거.
  · close_refunded(refunded)  : refund_followup(오류·환불) 경로 — 차감이 이미 보상됐음을 표기.
pending 으로 N분(>생성상한 185s) 넘게 남은 영수증 = 크래시 orphan → 리컨실(Step 3)이 멱등 환불.

모든 함수는 caller 트랜잭션 안에서 UPDATE/INSERT 만 한다(commit 은 caller 몫 — 차감/영속 커밋에 합류).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import AnswerReceipt


_SLOT_KINDS = ("cash", "free", "daily", "membership", "pass")


def open_receipt(
    db: Session, *, user_id: Optional[int], menu: str, ref_id: Optional[str], amount: int,
    slot_kind: str = "cash", pass_id: Optional[int] = None,
) -> Optional[int]:
    """pending 영수증 생성 후 id 반환. 회원(user_id)이고 실현금(amount>0) 또는 무료슬롯 소비 시에만.

    caller 의 선점/차감 커밋에 합류하도록 flush 만 한다(별도 커밋 안 함)."""
    if not user_id:
        return None
    if slot_kind == "cash" and amount <= 0:
        return None                        # 무과금·무슬롯(관리자 등) → 대상 아님
    r = AnswerReceipt(
        user_id=user_id, menu=menu, ref_id=ref_id, amount=int(amount),
        slot_kind=slot_kind, pass_id=pass_id, status="pending",
    )
    db.add(r)
    db.flush()
    return r.id


def open_for_bill(
    db: Session, *, user_id: Optional[int], menu: str, ref_id: Optional[str],
    bill: dict, charged: int,
) -> Optional[int]:
    """bill 로부터 slot_kind/amount/pass_id 를 판정해 pending 영수증 생성 — 현금·무료슬롯 orphan 공통 진입점.

    현금(charged>0)=cash, 그 외는 소비한 무료슬롯 종류(membership/pass/free/daily). 무과금·무슬롯이면 None."""
    if charged and charged > 0:
        return open_receipt(db, user_id=user_id, menu=menu, ref_id=ref_id, amount=int(charged), slot_kind="cash")
    if bill.get("use_membership"):
        return open_receipt(db, user_id=user_id, menu=menu, ref_id=ref_id, amount=0, slot_kind="membership")
    if bill.get("use_pass_free"):
        return open_receipt(db, user_id=user_id, menu=menu, ref_id=ref_id, amount=0,
                            slot_kind="pass", pass_id=bill.get("pass_id"))
    if bill.get("use_free_quota"):
        return open_receipt(db, user_id=user_id, menu=menu, ref_id=ref_id, amount=0, slot_kind="free")
    if bill.get("use_daily_free"):
        return open_receipt(db, user_id=user_id, menu=menu, ref_id=ref_id, amount=0, slot_kind="daily")
    return None


def finalize_receipt(
    db: Session, receipt_id: Optional[int], *,
    message_id: Optional[int] = None, ref_id: Optional[str] = None,
) -> None:
    """pending → complete(EOF 도달). 조건부(status='pending')라 이미 환불/완료된 건은 no-op."""
    if not receipt_id:
        return
    vals: dict = {"status": "complete", "finalized_at": datetime.utcnow()}
    if message_id is not None:
        vals["message_id"] = message_id
    if ref_id is not None:
        vals["ref_id"] = ref_id            # dream: 생성 후에야 tool_id 확정 → 여기서 링크 교정
    db.execute(
        update(AnswerReceipt)
        .where(AnswerReceipt.id == receipt_id, AnswerReceipt.status == "pending")
        .values(**vals)
    )


def close_refunded(db: Session, receipt_id: Optional[int]) -> None:
    """pending → refunded(오류·환불 경로). 조건부라 이미 완료/환불이면 no-op. 리컨실이 재환불하지 않게 한다."""
    if not receipt_id:
        return
    db.execute(
        update(AnswerReceipt)
        .where(AnswerReceipt.id == receipt_id, AnswerReceipt.status == "pending")
        .values(status="refunded", finalized_at=datetime.utcnow())
    )


def _restore_slot(db: Session, user_id: int, slot_kind: str, pass_id: Optional[int]) -> None:
    """무료/일일/멤버십/pass 슬롯 orphan 복원 — 선점(claim)의 역연산. _refund_free_claim 과 동일 규칙이나
    bill 이 아닌 slot_kind 로 분기(리컨실은 bill 이 없다). 조건부 UPDATE 라 카운터가 음수로 가지 않는다."""
    from backend.app.repositories.auth_models import User

    if slot_kind == "free":
        db.execute(update(User).where(User.id == user_id, User.free_used_count > 0)
                   .values(free_used_count=User.free_used_count - 1))
    elif slot_kind == "daily":
        db.execute(update(User).where(User.id == user_id).values(daily_free_used_at=None))
    elif slot_kind == "membership":
        db.execute(update(User).where(User.id == user_id, User.membership_used_count > 0)
                   .values(membership_used_count=User.membership_used_count - 1))
    elif slot_kind == "pass" and pass_id:
        from backend.app.services import pass_service
        pass_service.refund_free_basic(db, pass_id)


def reconcile_orphans(db: Session, *, older_than_min: int = 20, limit: int = 500) -> int:
    """크래시 orphan(선점 O·완결 X) 멱등 복구 — 스케줄러가 주기 호출. 복구한 건수 반환.

    'pending 으로 older_than_min(>생성상한 185s, 기본 20분) 넘게 남은 영수증' = 선점됐지만 EOF(완결)
    도달 못 한 크래시 orphan. 정상 답변은 done 에서 complete, 오류는 refund_followup/_refund_free_claim 에서
    refunded 로 이미 마감돼 대상이 아니다.

    각 영수증을 status='pending'→'refunded' 로 '조건부 선점(승자만, 행잠금)'한 뒤 같은 트랜잭션에서 복구:
      · cash: 멱등 환불 adjust_credit(idem_key=receipt:{id}:refund)
      · free/daily/membership/pass: 슬롯 카운터 복원(_restore_slot). 멱등성은 상태 조건부 전이(승자독점)가 보장.
    레이스: 다른 곳이 먼저 complete/refunded 면 rowcount=0 → 건너뜀(오복구 없음); 동시 리컨실도 행잠금으로 1승자.
    """
    from backend.app.services import auth_service

    cutoff = datetime.utcnow() - timedelta(minutes=max(1, older_than_min))
    rows = db.execute(
        select(AnswerReceipt)
        .where(AnswerReceipt.status == "pending", AnswerReceipt.created_at < cutoff)
        .limit(limit)
    ).scalars().all()
    recovered = 0
    for r in rows:
        won = db.execute(
            update(AnswerReceipt)
            .where(AnswerReceipt.id == r.id, AnswerReceipt.status == "pending")
            .values(status="refunded", finalized_at=datetime.utcnow())
        ).rowcount
        if won != 1:
            db.rollback()          # 그 사이 완결/환불됨 → 오복구 방지
            continue
        try:
            if not r.user_id:
                pass
            elif (r.slot_kind or "cash") == "cash":
                if r.amount and r.amount > 0:
                    auth_service.adjust_credit(
                        db, r.user_id, r.amount, reason="orphan_refund",
                        ref_id=r.ref_id, idem_key=f"receipt:{r.id}:refund",
                    )
            else:
                _restore_slot(db, r.user_id, r.slot_kind, r.pass_id)
            db.commit()            # 상태 전이 + 복구를 원자적으로 확정
            recovered += 1
        except Exception:          # noqa: BLE001 — 개별 복구 실패는 다음 주기 재시도(상태도 롤백)
            db.rollback()
    return recovered


def purge_terminal(db: Session, *, older_than_days: int = 7) -> int:
    """완결·환불로 마감된 오래된 영수증 정리(테이블 무한증가 방지). pending 은 절대 지우지 않는다."""
    cutoff = datetime.utcnow() - timedelta(days=max(1, older_than_days))
    res = db.execute(
        delete(AnswerReceipt).where(
            AnswerReceipt.status.in_(("complete", "refunded")),
            AnswerReceipt.finalized_at.isnot(None),
            AnswerReceipt.finalized_at < cutoff,
        )
    )
    db.commit()
    return int(res.rowcount or 0)
