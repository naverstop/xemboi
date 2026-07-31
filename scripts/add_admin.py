# -*- coding: utf-8 -*-
"""관리자 계정 추가/승격(운영용).

사용:  .venv\\Scripts\\python.exe -m scripts.add_admin <email> <password>

- 계정이 없으면: 해당 비밀번호로 role=admin 생성(must_change_password=False).
- 이미 있으면: role=admin 승격 + 비밀번호를 주어진 값으로 설정.
- 두 경우 모두 관리자 시드 크레딧(admin_seed_credits) 미만이면 보충.
운영 DB(Postgres)에 직접 반영된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python -m scripts.add_admin <email> <password>")
        return 2
    email = sys.argv[1].strip().lower()
    password = sys.argv[2]

    from backend.app.core.config import get_settings
    from backend.app.core.db import get_session_factory
    from backend.app.core.security import hash_password
    from backend.app.services import auth_service

    s = get_settings()
    sf = get_session_factory()
    with sf() as db:
        u = auth_service.get_user_by_email(db, email)
        if u is None:
            u = auth_service.create_user(
                db, email=email, password=password, role="admin",
                must_change_password=False, nickname=email.split("@")[0],
            )
            action = "생성"
        else:
            u.password_hash = hash_password(password)
            u.role = "admin"
            u.must_change_password = False
            db.flush()
            action = "승격/갱신"
        bal = auth_service.get_balance(db, u.id)
        if bal < s.admin_seed_credits:
            auth_service.adjust_credit(db, u.id, s.admin_seed_credits - bal, reason="admin_seed")
        db.commit()
        print(f"[admin {action}] id={u.id} email={u.email} role={u.role} "
              f"balance={auth_service.get_balance(db, u.id)} must_change_pw={u.must_change_password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
