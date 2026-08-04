# 개인정보 유출 대응 런북 (H3 — 개인정보보호법 제34조)

> 목적: 개인정보 유출(의심 포함) 발생 시 **탐지 → 통지 → 신고 → 조치**를 지연 없이 수행하기 위한 절차.
> 근거: 개인정보보호법 제34조(유출등의 통지·신고), 안전성 확보조치 기준 제8조(접속기록).

## 1. 탐지 (Detection)
- **접속기록**: 관리자/상담사의 회원 PII 접근·인증 이벤트가 `access_logs`에 기록된다(행위자 user_id·경로(대상 회원 id 포함)·method·status·ip·시각). 미들웨어: `backend/app/core/access_log.py`.
- **이상탐지(자동)**: 한 계정이 5분 내 관리자 PII 경로(`/api/admin%`)를 100회 이상 호출하면 서버 로그에 `SECURITY: 대량 관리자 PII 조회 의심` 경고가 남는다. 임계값은 `access_log.py`의 `_BULK_THRESHOLD`/`_BULK_WINDOW_SEC`.
- **정기 점검(수동)**: 월 1회 이상 `access_logs`를 점검한다.
  ```sql
  -- 계정별 최근 24h 관리자 PII 접근 상위
  SELECT user_id, count(*) FROM access_logs
  WHERE path LIKE '/api/admin%' AND created_at > now() - interval '24 hours'
  GROUP BY user_id ORDER BY 2 DESC;
  -- 권한거부(403) 시도(무단 접근 흔적)
  SELECT user_id, path, count(*) FROM access_logs
  WHERE status IN (401,403) AND created_at > now() - interval '7 days'
  GROUP BY user_id, path ORDER BY 3 DESC;
  ```
- 접속기록은 **최소 1년 보관**하고 위·변조되지 않도록 관리한다(정기 백업).

## 2. 통지 (Notification) — 정보주체
- 유출을 알게 된 때에는 **지체 없이(72시간 이내)** 해당 정보주체에게 아래를 통지한다.
  1. 유출된 개인정보 항목  2. 유출 시점·경위  3. 피해 최소화를 위해 정보주체가 할 수 있는 방법
  4. 사업자의 대응·구제 절차  5. 신고 접수 담당부서·연락처(개인정보 보호책임자)
- 통지 수단: 가입 이메일(서비스 내 SMTP) + 공지. 연락처 부재 시 홈페이지 30일 이상 게시.

## 3. 신고 (Report) — 규제기관
- **1천 명 이상** 정보주체의 개인정보가 유출된 경우, 또는 민감정보/고유식별정보 유출 시 **72시간 이내**
  개인정보보호위원회(PIPC) 및 한국인터넷진흥원(KISA)에 신고한다. (privacy.go.kr / 국번없이 118)

## 4. 조치 (Containment)
- 유출 경로 차단: 문제 계정 즉시 비활성/토큰 폐기, 필요 시 시크릿(JWT/AES/DB/LLM 키) 로테이션.
- 영향범위 산정: `access_logs`로 유출 시점 전후 접근 계정·대상 회원·조회 규모 확정.
- 재발방지: 접근권한 재점검(최소권한, `ADMIN_EMAILS` = 소유자만), 필요 시 임계값/모니터링 강화.

## 5. 책임자
- 개인정보 보호책임자(DPO): **[지정 필요 — 이름·직위·연락처를 개인정보처리방침과 여기에 기재]**
- 이관·판매 시 인수자에게 본 런북과 `access_logs` 점검 의무를 함께 승계한다.

---
*참고: 접근기록·이상탐지(자동 경고)는 코드로 구현됐으나, 통지·신고·정기점검은 운영 담당자가 수행하는 절차다. 규모(1천/1만 명)·기한은 최신 법령으로 확인할 것.*
