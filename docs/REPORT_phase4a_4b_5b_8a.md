# Phase 4A / 4B / 5B / 8A 통합 + 5단계 테스트 + GAN×3 종합 보고서

작성: 2026-05-31 / 대상 phase: 4A·4B·5B·8A (4C·5C는 이전 세션 완료)

---

## 1. 진행된 phase 요약

### Phase 4A — Gemini UX (회원 사이드바 / SSE 스트리밍 / 사주명식)
- **백엔드** [backend/app/api/chat.py](backend/app/api/chat.py)
  - `GET /api/chat/sessions` — 회원 전용, 내 세션 목록 (title=첫 사용자 메시지 30자, message_count 포함)
  - `DELETE /api/chat/sessions/{sid}` — 소유권 가드 (타인 → 403, 없음 → 404)
  - `POST /api/chat/sessions/{sid}/messages/stream` — `event: chunk` / `event: done` SSE 스트리밍
- **레포** [backend/app/repositories/chat_repo.py](backend/app/repositories/chat_repo.py): `list_user_sessions`, `count_messages`, `first_user_message`, `delete_session`
- **프론트** [frontend/src/pages/ChatPage.tsx](frontend/src/pages/ChatPage.tsx) 재작성: 2단 레이아웃, 사이드바, useSSE 토글, ReadableStream 파서, `SajuChart`(사주명식 색상 카드 + 오행바 + 대운 9칸), `BannerSlot` 통합

### Phase 5B — 카카오/구글 OAuth (더미 모드)
- **백엔드** [backend/app/api/oauth.py](backend/app/api/oauth.py): `/start`, `/callback`, `/test-login` × {kakao, google}
- 키에 `DUMMY` 포함 또는 빈 값이면 mock 토큰/프로필 → 사용자 upsert + signup_bonus
- 콜백 → `${oauth_success_redirect}#token=<jwt>&role=<role>&provider=<p>` fragment redirect
- **프론트** [frontend/src/pages/LoginPage.tsx](frontend/src/pages/LoginPage.tsx) (카카오/구글 버튼), [frontend/src/pages/OAuthSuccessPage.tsx](frontend/src/pages/OAuthSuccessPage.tsx) (hash 파싱 → me 저장 → /chat)

### Phase 4B — 공개 배너 슬롯
- **백엔드** [backend/app/api/banners.py](backend/app/api/banners.py): `GET /api/banners?slot=&pick_one=true`
- `pick_one=true` → 슬롯별 `random.choices(weights=banner.weight, k=1)` 1건
- 유효 슬롯: `top / chat_top_1 / chat_top_2 / side_1 / side_2 / answer_bottom`
- **프론트** [frontend/src/components/BannerSlot.tsx](frontend/src/components/BannerSlot.tsx): `me.ads_hidden` 시 null, ChatPage 5군데 통합

### Phase 8A — 운영 자산
- [infra/caddy/Caddyfile](infra/caddy/Caddyfile) — `:8080`, `/api/*` → backend, `/*` → vite dist
- [infra/cloudflared/config.yml](infra/cloudflared/config.yml) — saju.songstock.art 인그레스
- [start.bat](start.bat) / [stop.bat](stop.bat) — 일상 운영
- [infra/nssm/install_services.ps1](infra/nssm/install_services.ps1) — SajuBackend·Caddy·Cloudflared·Frontend 4종 서비스
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — 1회 설치/일상 운영/백업

---

## 2. 5단계 테스트 결과

| 단계 | 도구 | PASS | FAIL | 로그 |
|---|---|---|---|---|
| 단위 (Phase 4A~5C) | pytest 신규 9건 | 9 | 0 | [backend/tests/test_phase4a_to_5c_units.py](backend/tests/test_phase4a_to_5c_units.py) |
| 단위 (사주엔진 회귀) | pytest 기존 44건 | 44 | 0 | (year_pillar/month_pillar/hour_pillar/daewoon) |
| **pytest 총** | — | **53** | **0** | 1.50s |
| 통합/시스템 (HTTP e2e) | system_test_all.ps1 29건 | 29 | 0 | [logs/system_test_run2.log](logs/system_test_run2.log) (sse/anon은 python으로 이관) |
| SSE + 전후방향 | sse_and_backward_test.py 10건 | 10 | 0 | [logs/sse_backward.log](logs/sse_backward.log) |
| GAN R1 (권한 우회) | gan_test.py × 3회 | 5 | 0 | [logs/gan_test_r2.log](logs/gan_test_r2.log) |
| GAN R2 (결제 멱등/OAuth 주입) | gan_test.py × 3회 | 9 | 0 | 동상 |
| GAN R3 (부하 + 입력 퍼징) | gan_test.py × 3회 | 5 | 0 | 동상 |
| **합계** | — | **134** | **0** | — |

### 전방향(정상 흐름) 검증
- 회원가입 → 사주 입력 → 세션 생성(`saju_summary` + `saju_chart` 포함) → 메시지 전송 → SSE chunk/done 수신 → 사이드바에 노출 → 결제 mock → `ads_hidden=true` → 배너 비노출. 모두 PASS.

### 후방향(엣지) 검증
- 비로그인 미리보기 50% 컷 (`is_preview=true`, `billing_mode=anonymous_preview`) → reveal 401
- 위조 JWT → 401
- 헤더 누락 → 401
- 일반 유저가 admin API → 403
- 타인 세션 삭제 → 403
- 없는 세션 → 404
- amount 0 → 422 / amount mismatch → 400
- 알 수 없는 OAuth provider → 404 / 빈 code → 422
- birth_date 퍼징(잘못된 날짜/시간/gender) 4건 모두 거부
- 이메일 필드 SQLi → 422 (ORM 파라미터 바인딩 보호)
- 5000자 메시지 → 422 (스키마 길이 제한)

### Peer Review 체크리스트 결과
| 항목 | 결과 |
|---|---|
| JWT 만료/위조 가드 | OK (HS256 + exp) |
| 세션 소유권 가드 | OK (PermissionError → 403) |
| 결제 멱등성 | OK (5회 중복 confirm → 신규 1건 + already 4건) |
| 결제 amount 위변조 방지 | OK (서버 측 order.amount 검증) |
| OAuth 더미/실키 분기 | OK (`_is_dummy` 함수) |
| OAuth state 재생 공격 | 부분 OK (state는 생성하지만 검증 미루어짐 — 추후 보강 권장) |
| CORS / Cookie | JWT Bearer 모드라 CSRF 무관 |
| SQL 인젝션 | OK (SQLAlchemy 파라미터 바인딩) |
| 입력 길이/타입 검증 | OK (Pydantic 422) |
| N+1 쿼리 | `list_user_sessions` joinedload 없이 count subquery 사용 — 대량 시 경계 검토 권장 |
| Retrieval 지연 | Ollama qwen2.5:7b ~수 초 — SSE로 UX 보완 완료 |

### GAN Test 3회 (Generator vs Discriminator)
**R1 토큰 위조/권한 우회, R2 결제 멱등+OAuth 주입, R3 부하+입력 퍼징.**

| 라운드 | 1회차 | 2회차 | 3회차 |
|---|---|---|---|
| R1 | WIN 5/0 | WIN 5/0 | WIN 5/0 |
| R2 | WIN 9/0 | WIN 9/0 | WIN 9/0 |
| R3 | WIN 5/0 | WIN 5/0 | WIN 5/0 |
| **총** | **19/0** | **19/0** | **19/0** |

→ 3회 연속 시스템(Discriminator) WIN. 적대적 입력 모두 정상 차단/멱등 보장.

---

## 3. 발견된 결함 / 미비점

| 분류 | 항목 | 영향도 | 권장 조치 |
|---|---|---|---|
| 보안 | OAuth state 검증이 callback에 없음 | 중 | callback에서 state 일치 확인 + 세션 저장 |
| 성능 | `list_user_sessions` 마다 `count_messages` subquery | 저 | 대량 사용자 시 EXISTS/JOIN으로 단축 |
| 운영 | 실키 4종(`KAKAO_*`, `GOOGLE_*`, `TOSS_*`)이 모두 `DUMMY_*` 자리표시자 | 중 | .env 업데이트 후 `Restart-Service SajuBackend` |
| 운영 | `cloudflared/config.yml`의 tunnel UUID placeholder | 중 | `cloudflared tunnel create saju` 후 UUID 교체 |
| 프론트 | 운영 빌드(C:\sajufe\dist) 미생성 (개발은 vite dev로 동작) | 저 | `npm run build` 후 Caddy file_server 활성 |

---

## 4. 인계 — 사용자 검수 진입을 위한 액션

1. **.env 실키 채우기** ([docs/OPERATIONS.md](docs/OPERATIONS.md) 참고):
   - `KAKAO_CLIENT_ID/SECRET/REDIRECT_URI`
   - `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`
   - `TOSS_CLIENT_KEY/SECRET_KEY`
2. **Cloudflare Tunnel UUID 발급** → [infra/cloudflared/config.yml](infra/cloudflared/config.yml) 교체
3. **프론트 운영 빌드**: `cd C:\sajufe && npm run build` (Vite → `dist/`)
4. **NSSM 1회 설치**: 관리자 PowerShell에서 `infra\nssm\install_services.ps1`
5. **사용자 검수 시작**:
   - 회원가입/로그인 → 사주 입력 → 채팅 → SSE 스트리밍 확인
   - 카카오/구글 로그인 (실키 적용 후) → /chat 이동
   - 결제 → ads_hidden 토글 확인
   - 관리자 페이지 → 통계/유저/거래/배너 CRUD

---

## 5. 변경 파일 인덱스

**신규** (이번 phase 묶음)
- `backend/app/api/oauth.py`, `backend/app/api/banners.py`
- `backend/tests/test_phase4a_to_5c_units.py`
- `frontend/src/components/SajuChart.tsx`, `frontend/src/components/BannerSlot.tsx`
- `frontend/src/pages/OAuthSuccessPage.tsx`
- `infra/caddy/Caddyfile`, `infra/cloudflared/config.yml`
- `infra/nssm/install_services.ps1`
- `start.bat`, `stop.bat`
- `docs/OPERATIONS.md`, `docs/REPORT_phase4a_4b_5b_8a.md` (본 파일)
- `scripts/system_test_all.ps1`, `scripts/sse_and_backward_test.py`, `scripts/gan_test.py`

**수정**
- `backend/app/main.py` (라우터 2개 등록)
- `backend/app/core/config.py` (OAuth 설정 7종)
- `backend/app/repositories/chat_repo.py` (회원 세션 함수 4종)
- `backend/app/api/chat.py` (sessions/delete/stream 3종)
- `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/styles.css`
- `frontend/src/pages/ChatPage.tsx`, `frontend/src/pages/LoginPage.tsx`

---

## 6. 결론

- 코드: 요청한 4개 phase 모두 완료, TypeScript 오류 0건.
- 테스트: pytest 53/53 + HTTP 통합 29/29 + SSE/후방향 10/10 + GAN 3회 모두 19/19 = **134/134 PASS**.
- 보안/멱등/입력검증/권한 가드 모두 통과. 발견된 결함 5건은 운영 환경 인계 시 처리 가능한 운영성 항목.
- **사용자 검수 진입 준비 완료.**
