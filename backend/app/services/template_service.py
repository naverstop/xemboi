"""답변 표준양식/로직 관리(계획 L). 활성 템플릿 body가 SYSTEM_PROMPT로 주입된다.

활성 템플릿이 없으면 DEFAULT_SYSTEM_PROMPT 폴백. 캐시는 짧게(설정 변경 즉시 반영 위해
관리자 변경 시 invalidate). 버전 관리: 같은 name 으로 새로 만들면 version 증가.
"""
from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import AnswerTemplate

DEFAULT_SYSTEM_PROMPT = """당신은 수십 년 경력의 대한민국 최고 사주명리 전문가이자 상담가입니다.

⚠️ 언어 규칙 (가장 중요 · 반드시 준수):
- 모든 문장을 100% 한국어로만 작성하세요. 중국어(간체/번체) 문장·단어를 절대 사용하지 마세요.
- 참고자료가 주어졌고 거기에 한문이나 중국어가 포함되어 있어도, 그 내용을 한국어로 풀어서 설명하세요(문장을 그대로 베끼지 말고 뜻을 풀어 쓰라는 뜻이며, 자료가 주어진 경우 그 판단 자체는 따르세요).
- 한자 용어는 단독으로 쓰지 말고 반드시 "한글(한자)" 병기 형식으로만 표기하세요. 예: 일간(日干), 정관(正官), 비견(比肩), 대운(大運).

원칙:
1. 당신의 전문 지식을 바탕으로 근거 있는 풀이만 하되, 명식에 없는 사실(간지·신살·합충·대운 등)은 절대 지어내지 마세요.
2. 자료·출처·문헌을 언급하지 말고("자료에 의하면", "참고자료에 따르면" 등 금지), 전문가 본인의 풀이로 직접 자신 있게 설명하세요.
   단 이는 **말투**에 대한 규칙입니다 — [참고자료]가 **주어진 경우에 한해**, 해석·관법이 자료와 당신의 일반 지식이 다르면 자료를 따르되 그 판단을 본인 풀이처럼 말하세요. 참고자료가 없으면 명식 계산값과 명리 원리로만 풀이하고, 책·문헌 이름을 지어내지 마세요.
3. 길흉 단정은 피하고, 확실하지 않은 부분은 가능성과 흐름으로 설명하세요.
4. 응답은 A4 용지의 약 70%를 채우는 충분한 분량(최소 1,200자 이상, 12~18문장)으로 작성하세요. 짧게 끝내지 말고 깊이 있게 풀어 주세요.
5. 사주명식 근거(일간 강약·오행·십성·대운/세운) → 해석 → 실생활 조언의 흐름으로 단락을 나눠 구체적으로 설명하세요. 각 핵심 포인트는 근거와 함께 풀어 주세요.
"""

_active_cache: str | None = None
_cache_loaded = False
_lock = threading.Lock()


def invalidate() -> None:
    global _cache_loaded, _active_cache
    with _lock:
        _active_cache = None
        _cache_loaded = False


def get_active_prompt(db: Session) -> str:
    """현재 활성 템플릿 body. 없으면 기본 프롬프트."""
    global _cache_loaded, _active_cache
    if _cache_loaded:
        return _active_cache or DEFAULT_SYSTEM_PROMPT
    with _lock:
        if not _cache_loaded:
            row = db.execute(
                select(AnswerTemplate)
                .where(AnswerTemplate.active.is_(True))
                .order_by(AnswerTemplate.version.desc(), AnswerTemplate.id.desc())
            ).scalars().first()
            _active_cache = row.body if row else None
            _cache_loaded = True
    return _active_cache or DEFAULT_SYSTEM_PROMPT


def _to_dict(t: AnswerTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "body": t.body,
        "version": t.version,
        "active": t.active,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


def list_templates(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(AnswerTemplate).order_by(AnswerTemplate.id.desc())
    ).scalars().all()
    return [_to_dict(t) for t in rows]


def create_template(
    db: Session, *, name: str, body: str, active: bool = False
) -> dict[str, Any]:
    # 같은 name 의 최대 version + 1
    max_v = db.execute(
        select(AnswerTemplate.version).where(AnswerTemplate.name == name)
        .order_by(AnswerTemplate.version.desc())
    ).scalars().first()
    version = (max_v or 0) + 1
    t = AnswerTemplate(name=name, body=body, version=version, active=active)
    db.add(t)
    db.flush()
    if active:
        _deactivate_others(db, keep_id=t.id)
    db.commit()
    db.refresh(t)
    invalidate()
    return _to_dict(t)


def update_template(db: Session, template_id: int, **fields: Any) -> dict[str, Any]:
    t = db.get(AnswerTemplate, template_id)
    if t is None:
        raise LookupError(f"template {template_id} not found")
    for k in ("name", "body"):
        if fields.get(k) is not None:
            setattr(t, k, fields[k])
    if fields.get("active") is True:
        t.active = True
        _deactivate_others(db, keep_id=t.id)
    elif fields.get("active") is False:
        t.active = False
    db.commit()
    db.refresh(t)
    invalidate()
    return _to_dict(t)


def activate_template(db: Session, template_id: int) -> dict[str, Any]:
    t = db.get(AnswerTemplate, template_id)
    if t is None:
        raise LookupError(f"template {template_id} not found")
    t.active = True
    _deactivate_others(db, keep_id=t.id)
    db.commit()
    db.refresh(t)
    invalidate()
    return _to_dict(t)


def delete_template(db: Session, template_id: int) -> None:
    t = db.get(AnswerTemplate, template_id)
    if t is None:
        raise LookupError(f"template {template_id} not found")
    db.delete(t)
    db.commit()
    invalidate()


def _deactivate_others(db: Session, keep_id: int) -> None:
    rows = db.execute(
        select(AnswerTemplate).where(
            AnswerTemplate.active.is_(True), AnswerTemplate.id != keep_id
        )
    ).scalars().all()
    for r in rows:
        r.active = False
    db.flush()
