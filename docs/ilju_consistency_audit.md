# 일주·일진·월주 재발 버그 전수감사 (2026-07-09, Workflow 31-에이전트)

전문가 지적: 무신 일주 사용자에게 일간 계(癸) 표시. 매번 고쳐도 재발하는 근본원인 규명·재발방지.
검증: 74개 명식계산 경로 인벤토리 + 22건 일주시프트 실측재현.

---

# 사주 명식(일주/일간/월주/일진) 버그 재발 근본원인 분석 및 재발방지 설계 보고서

작성일: 2026-07-09 / 대상 브랜치: `feat/roadmap-consult-newyear`(실코드) / 근거: 전수 인벤토리 30경로 + 확정 불일치 22건(모두 `.venv`로 일주 시프트 실측 재현됨)

---

## 1. 왜 고쳐도 매번 재발하는가 — 시스템적 근본원인

증상(일간이 틀림 → 십성·용신·오행 연쇄 오류)은 개별 페이지 버그가 아니라 **아키텍처 결함 4종**의 합성이다. 한 기능을 고쳐도 나머지가 같은 결함을 공유하므로 재발한다.

### 근본원인 A — 정규화 파라미터 기본값의 3중 분열 (가장 치명적)
일주를 하루 밀 수 있는 핵심 플래그 `apply_true_solar_time`의 기본값이 계층마다 정반대다.

| 계층 | 기본값 | 근거 |
|---|---|---|
| 엔진 캐논 `BirthInput` | **False** | `backend/app/saju/types.py:30` |
| 저장 프로필 `ProfileReq` / DB 컬럼 | **False** | `profiles.py:33`, `auth_models.py:355` |
| 요청 DTO `BirthDTO` | **True** | `chat_dto.py:23` |
| 즉석 DTO `AmuletReq/SnackReq/ShareCardReq/BirthBody` | **True** | `amulet.py:31`, `snack.py:23`, `share_card.py:25`, `compat_invite.py:60` |
| 프론트 전 페이지 폼 초기 state | **true** | `TodayPage.tsx:37`, `ChatPage.tsx:90` 등 |

`night_zi_mode`도 마찬가지로 분열: 프로필 `None`(`profiles.py:36`) vs 소비 DTO `"yaja"`(`chat_dto.py:26`). 게다가 `None`을 `BirthInput`에 직접 넣으면 `ValidationError`(literal)라, 소비자마다 `or "yaja"` 가드를 반복해야 하는 취약 불변식이다(현재 `compat_service.py:73`만 방어).

→ **같은 birth라도 '어느 DTO를 거치느냐'로 일주가 갈린다.**

### 근본원인 B — 진태양시(-32분) × 자동 00:30 시각의 결합
- 서울 경도 보정량 = (126.98 − 135)×4 ≈ **−32분** (`pillars.py:84-92`).
- 프론트는 시각 미입력을 조용히 **`"00:30"`**으로 채운다 (`birthTime.ts:8` `DEFAULT_BIRTH_TIME`).
- 00:30 − 32분 = **전날 23:58** → `compute_pillars`가 `adj_d`(보정된 날짜)로 `getDayGZ`를 뽑으므로(`pillars.py:117-120`) **일주가 하루 통째로 밀린다.**
- 즉 시각을 안 넣은 사용자는 정확히 롤오버 위험창(00:00~00:31) 한복판에 놓인다. 실측: 00:30 births 표본 **48/48(=100%)**, 2001년 **151/365일**에서 true_solar on/off가 일주를 뒤집음.

핵심 설계 결함: **진태양시(경도·균시차)는 명리학적으로 '시주(時) 결정'에만 써야 하는데, 현재 코드는 일주(日)의 달력일 경계까지 이동시킨다.** sub-hour 보정이 day pillar를 바꾸는 것 자체가 버그.

### 근본원인 C — '단일 진실' 저장소가 실제로는 이중 + 무검증
"저장 프로필"이라 불리는 저장소가 **둘로 갈라져 있고 기본값이 상반**된다.
- **후보 A**: `SajuProfile` 테이블(`profiles.py`, 가족/궁합용) — true_solar 기본 **False**.
- **후보 B**: `User.saju_profile` JSON blob(`auth.py:294`, 전 메뉴 자동채움 소스) — 스키마 없는 free dict를 `json.dumps`로 **검증·정규화 없이** 저장, `/me`가 그대로 반환. 통상 true로 저장됨.

SettingsPage 가족프로필 수정은 A에, ChatPage '기억하기'는 B에 쓴다. 궁합은 A를, `/today`·push는 B를 읽는다 → **같은 사람이 궁합과 오늘의운세에서 다른 일주**를 볼 수 있다. 게다가 신규 프로필 기본 시각이 SettingsPage는 `"12:00"`(`SettingsPage.tsx:175`), 기능 폼은 `"00:30"`이라 '무입력' 의미조차 저장소마다 다른 일주를 낸다.

### 근본원인 D — 엔드포인트마다 손으로 필드를 골라 넘김(파라미터 드롭)
BirthDTO→BirthInput 변환에 **공용 헬퍼가 없어** 각 엔드포인트가 필드를 개별 나열한다. 그 결과 조용한 누락이 산재한다.

| 경로 | 드롭되는 파라미터 | 근거 |
|---|---|---|
| `/api/saju/chart` (post_chart) | `night_zi_mode`, `birth_longitude`, `apply_equation_of_time` | `saju.py:35-42` |
| `snack` | `apply_equation_of_time` (SnackReq에 필드 자체가 없음) | `snack.py:17-26` |
| `compat_invite` | `apply_equation_of_time` (BirthBody에 필드 없음) | `compat_invite.py:54-62` |
| `dream` | `apply_true_solar_time`, `birth_longitude`, `apply_equation_of_time`, `night_zi_mode` **4종 전부** | `dream.py:35-42, 74-77` |
| `push_service` | `profile.get(k) is not None` 필터라 저장 안 된 키는 엔진 기본(False)로 폴백 | `push_service.py:206` |

같은 `saju.py` 안에서 `/today`(6종 전달)와 `/chart`(3종 드롭)가 공존 → **형제 엔드포인트끼리도 일주가 다를 수 있음.**

**요약**: A(기본값 분열) + B(진태양시×00:30) + C(이중 무검증 저장소) + D(수동 필드 나열)가 맞물려, 어떤 단일 페이지를 고쳐도 다른 경로가 같은 4개 결함을 공유하므로 재발한다.

---

## 2. 이번 실측(일간 계癸 vs 무戊, 월간지)의 정확한 발생 경로

증상은 **두 개의 서로 다른 원인**이 겹친 것이며, 분리해서 봐야 한다.

### (가) 일간 오류(계 vs 무) — 결정적 엔진 경로 + LLM 오독의 복합
1. 이 사용자의 정본 일주는 무신(戊申), 일간 무(戊). 그런데 화면엔 계(癸)로 표시됨.
2. **1간 시프트(무↔정, 계↔임 등)는 근본원인 A+B로 결정적으로 발생 가능**하다. 예: `/today`가 저장 프로필이 아닌 요청 BirthDTO(true_solar 기본 True) + 자동 00:30으로 `build_chart`를 재계산(`saju.py:70-86`, `u_stem=chart.pillars.day.stem`). 실측 재현: 1994-08-15을 시모름/true_solar=False로 계산 → 癸酉(일간 癸), 00:30+true_solar=True로 계산 → 壬申(일간 壬). 오늘(2026-07-09, 일진 甲) 기준 십성도 상관→식신으로 연쇄 변동.
3. 그러나 **戊→癸는 5간 차이**로, ±1일 파라미터 시프트만으로는 설명 불가. 이 특정 표시값(戊를 癸로)은 **채팅 LLM이 `saju_summary` 텍스트를 오독한 환각**이다. `/today`라는 실제 엔드포인트/페이지의 계산 결과가 아니라, 채팅 경로(`chat_service.py`)에서 LLM(Ollama)이 저장된 요약 텍스트를 보고 일간을 오독한 것. `_verify_day_stem`(`chat_service.py:787-802`)이 `'일간 …(漢)'` **한자 표기에만 발화**하고 한글전용('일간 계수') 표기는 미포착하는 **검증 갭**이 이를 통과시켰다.

→ 결론: 무↔정 같은 인접 시프트는 엔진 경로(A+B)가 결정적으로 유발, 무→계 같은 원거리 오표시는 LLM 환각 + 검증 갭. **둘 다 고쳐야 한다.**

### (나) 월간지 오류(2025 갑신/을유 vs 2026 을미/병신) — 순수 LLM 환각/stale
- 엔진은 2026 병오년 월건을 **결정적으로 정확히** 계산한다(을미월·병신월·정유월…). `_upcoming_months`(`chat_service.py:1877-1901`)·`_current_luck_block`(`1935-1996`)이 오늘 일진·월운·세운을 산출해 `_build_user_prompt`(`2154`)로 두 핸들러 모두에 주입함을 실측 확인.
- 즉 '2026 월간지 미계산/미주입' 가설은 **반증됨**. 화면의 2025 패턴(갑신/을유)은 정답이 주입된 상태에서 **약한 1차 LLM이 무시했거나 stale 배포**된 것.
- 다만 `_verify_month_ganji`(`chat_service.py:1156`)는 **chat 경로에서만** 호출되고 `tool_service`·`compat_service` 스트림 검증 트리거엔 미포함이라, tool/compat 경로의 월간지 단독 환각은 교정 게이트가 안 열린다.

---

## 3. 재발방지 설계

### (a) birth 정규화를 한 곳으로 모으는 단일 함수/계약

모든 경로가 반드시 통과하는 **단일 서버측 리졸버**를 신설한다.

```
backend/app/saju/birth_resolver.py  (신규)

def resolve_birth_input(
    *, raw: dict | BirthDTO | SajuProfile | None,
    stored_profile: dict | None = None,   # User.saju_profile (단일 진실)
) -> BirthInput:
    """
    유일한 BirthDTO/dict/Profile → BirthInput 변환 지점.
    - 6종 파라미터를 CANONICAL_DEFAULTS로 완전하게 채운다(누락 금지).
    - stored_profile이 있으면 그 정규화값을 우선(단일 진실).
    - night_zi_mode None → 'yaja' 강제 정규화.
    - '시각 미입력'과 '시 모름'을 동일 정책으로 수렴.
    """
```

- **계약**: `build_chart`/`compute_pillars`를 직접 호출하는 코드는 반드시 이 함수가 만든 `BirthInput`만 받는다. 엔드포인트가 손으로 `BirthInput(...)`을 조립하는 것을 금지(아래 (e) 린트 게이트로 강제).
- `chat_service._to_birth_input`, `tool_service._to_birth_input`, `compat_service._to_birth_input`(현재 3벌 중복)과 `saju.py`의 인라인 조립을 전부 이 함수로 대체.

### (b) 전 엔드포인트 기본값 통일안

`backend/app/saju/constants.py`에 **단일 캐논** 정의:

```
CANONICAL_DEFAULTS = {
    "apply_true_solar_time": True,     # 운영자 결정: 제품 기본 ON
    "night_zi_mode": "yaja",
    "birth_longitude": 126.98,          # DEFAULT_LONGITUDE
    "apply_equation_of_time": False,
    "timezone_offset_min": 540,         # (일주에 무영향 — 주석 명시)
    # birth_time 미입력 정책은 (c)에서 결정
}
```

- 이 상수 하나를 `BirthInput`(types.py:30), `ProfileReq`(profiles.py:33,36), DB server_default(auth_models.py:355,360), 모든 즉석 DTO, 프론트 폼 초기 state가 **참조**하도록 정렬. 하드코딩 기본값 제거.
- **주의**: 기본을 True로 통일하려면 (c)의 진태양시-일주 분리를 반드시 선행해야 한다(안 하면 00:30 사용자 전원 일주가 하루 밀림). 순서: **(c) 먼저 → 그 다음 (b)의 True 통일.**
- `night_zi_mode`는 DB에서 NOT NULL + default `'yaja'`로 정규화하고 기존 None 백필.

### (c) 진태양시가 일주를 밀지 못하게 하는 코어 수정 (★가장 중요)

`compute_pillars`/`_adjust_time`(`pillars.py:70-124`) 분리:
- **일주(日柱)·월주(月柱)·년주(年柱)는 표준시(civil date) 기준으로 산정.** getDayGZ/getMonthGZ/getYearGZ는 보정 전 `solar_d`로 뽑는다.
- **진태양시·경도·균시차 보정(adj_t)은 시주(時柱, getHourGZ) 및 야자/조자 관법에만 적용.**
- 이렇게 하면 −32분 보정이 달력일을 넘겨 일간을 하루 미는 결함이 **원천 제거**된다. (만세력 관행과도 일치.)
- 자정 인접 일주 경계는 야자/조자(night_zi_mode)로만 명시 처리.

**시각 미입력 정책 통일**: `birthTime.ts`의 blank→`"00:30"` 승격을 제거하고, 빈 시각은 '시 모름'과 동일하게 **`null`(시주 제외)** 로 처리하거나 시각 입력을 필수화. 두 표현이 같은 일주를 내야 한다. `ChatPage.tsx:184` 자동저장에서 blank→00:30 강제 저장 차단(프로필 오염 방지).

### (d) '같은 사용자 = 같은 일주' 불변식 교차검증 테스트

`backend/tests/test_ilju_invariant.py`(신규):

1. **경계 스윕 파라메트릭**: 자정±35분(00:00~00:35), 절입±35분, 23:00~23:59(야자 경계) 출생일 × 6종 파라미터 조합 → `compute_pillars`가 (c) 수정 후 **일주가 파라미터 토글에 불변**임을 assert(현재는 48/48 실패).
2. **크로스-엔드포인트 동일성**: 하나의 저장 프로필 fixture를 `/today`, `/chart`, `/calendar`, `chat.create_session`, `tool_service`, `compat_service`, `push_service.build_personal_iljin`에 각각 흘려 `chart.pillars.day.stem/branch`가 **전부 동일**한지 assert.
3. **저장소 일치**: `SajuProfile` 테이블과 `User.saju_profile` JSON이 같은 birth에 대해 같은 일주를 내는지.
4. **회귀 앵커**: 실측 케이스(1994-08-15, 2026-02-04 입춘, 2025-03-05 절입, 1988-02-04) 스냅샷 고정.
5. **검증 갭**: `_verify_day_stem`이 한글전용('일간 계수')·한자('일간 癸') 양쪽 모두 포착하는지.

### (e) 신규 기능이 또 어기지 못하게 하는 구조적 장치

1. **린트/CI 게이트**: `build_chart(`·`compute_pillars(`·`BirthInput(` 직접 호출을 `birth_resolver.py`·`pillars.py` 외부에서 금지하는 grep 기반 CI 체크(허용 목록 위반 시 빌드 실패).
2. **DTO 스키마 통합**: 즉석 DTO(AmuletReq/SnackReq/ShareCardReq/BirthBody/DreamReq)를 **공통 `BirthPayload` 베이스 클래스** 상속으로 통일 → 필드 누락(snack의 eot, dream의 4종) 구조적 차단.
3. **단일 진실 강제**: 로그인 사용자는 엔드포인트가 요청 body의 폼 기본값을 신뢰하지 말고, 서버가 `User.saju_profile`(정규화된 6종)로 **일주를 1회 계산해 스냅샷 캐시**하고 전 메뉴가 그 스냅샷을 읽게 한다(재계산 금지).
4. **월간지 검증 확산**: `_verify_month_ganji`를 `tool_service`·`compat_service` 스트림 검증 트리거에도 포함.

---

## 4. 구체적 수정 파일·라인 목록 (P0 → P1)

### P0 — 재발의 뿌리를 끊는 필수 수정 (이것만으로 90% 재발 차단)

| # | 파일·라인 | 조치 |
|---|---|---|
| P0-1 | `backend/app/saju/pillars.py:70-124` | **진태양시/경도/균시차 보정을 일주에서 분리**. getDayGZ/getMonthGZ/getYearGZ는 표준시 `solar_d` 기준, adj_t는 getHourGZ·야자/조자에만 적용. (근본원인 B 제거) |
| P0-2 | `frontend/src/lib/birthTime.ts:8,15-22` | blank→`"00:30"` 승격 제거. 빈 시각을 `null`(시주 제외)로 통일. `ChatPage.tsx:184` 자동저장의 00:30 강제 저장 차단 |
| P0-3 | `backend/app/saju/birth_resolver.py` (신규) + `backend/app/saju/constants.py` (신규 `CANONICAL_DEFAULTS`) | 단일 리졸버·단일 캐논 신설. (a)(b) |
| P0-4 | `backend/app/api/saju.py:35-42` (post_chart) | 드롭된 `night_zi_mode`·`birth_longitude`·`apply_equation_of_time` 전달 = `/today`와 동일화. 즉시 교정 |
| P0-5 | `backend/app/api/dream.py:35-42, 74-77, 181-182` | DreamReq에 정규화 4종 필드 추가 + build_chart에 전달. `birth_time=None` 하드코딩(182) → 실제 값 저장 |
| P0-6 | `backend/app/services/chat_service.py:787-802` (`_verify_day_stem`) | 한글전용 표기('일간 계수/무토') 포착하도록 정규식 확장. 무(戊)→계(癸) LLM 오독 상시 차단 |

### P1 — 통일·검증·구조적 방어

| # | 파일·라인 | 조치 |
|---|---|---|
| P1-1 | `types.py:30`, `profiles.py:33,36`, `auth_models.py:355,360`, `chat_dto.py:23,26`, `amulet.py:31`, `snack.py:23`, `share_card.py:25`, `compat_invite.py:60` | 6종 기본값을 `CANONICAL_DEFAULTS` 참조로 정렬. night_zi DB NOT NULL+`'yaja'` 백필 |
| P1-2 | `snack.py:17-26`, `compat_invite.py:54-62` | `apply_equation_of_time` 필드 추가(공통 `BirthPayload` 상속으로 일괄) |
| P1-3 | `backend/app/api/auth.py:282-298` (PUT /me/saju) | free dict 저장 금지 → 서버측 스키마+정규화 적용. 6종 완전성 보장 |
| P1-4 | `backend/app/services/push_service.py:206` | `is not None` 필터 폴백 제거 → `resolve_birth_input` 사용. 레거시 JSON 백필 1회 마이그레이션 |
| P1-5 | `backend/app/services/{chat,tool,compat}_service.py` (`_to_birth_input` 3벌) | 리졸버로 대체, 중복 제거 |
| P1-6 | `tool_service.py`·`compat_service.py` 스트림 검증 트리거 | `_verify_month_ganji` 포함(월간지 단독 환각 교정) |
| P1-7 | `frontend`: `SettingsPage.tsx:175`(신규 기본 12:00), `BirthFields.tsx:29-34`, 전 페이지 폼 초기 state | 시각 기본·true_solar 폴백을 캐논과 통일. `unknown_time`을 JSON 명시 필드로 영속화 |
| P1-8 | `backend/tests/test_ilju_invariant.py` (신규) + CI grep 게이트 | (d)(e) 불변식 테스트 + `build_chart/compute_pillars/BirthInput` 직접호출 금지 린트 |

### 배포 순서 주의
반드시 **P0-1(진태양시-일주 분리) → P1-1(기본값 True 통일)** 순. 순서가 뒤바뀌면 00:30 사용자 전원 일주가 하루 밀린다. 각 단계 후 P1-8 불변식 테스트로 게이트.

---

### 참고: 엔진은 무결한 부분 (건드리지 말 것)
- 월건/세운/일진의 **결정적 계산은 정확**(2026 병오년 을미/병신 확인). 월간지 오류는 LLM 환각/stale이지 엔진 결함 아님.
- `timezone_offset_min`(types.py:30, 기본 540)은 `_adjust_time`에서 **미사용(dead)** — 변경해도 일주 불변. 오해 방지 위해 주석 명시 또는 제거 권장.
- 타로(`tarot_service`)는 명식 비계산 → 이번 감사 무관.