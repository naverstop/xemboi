# VER — 유령 정산행(ghost settlement) 재검증

## 판정: CONFIRMED (심각도 medium→low 하향)

### 사실 검증(모두 재현됨)
- session 3974d3c8dac046cf838cea059778d34b: status=completed, accepted_at=NULL,
  started_at=NULL, credits_charged=0, price_p=50000, refunded=false, reservation_id=NULL.
  credit_transactions(ref_id=세션) 0건 = 한 번도 차감/결제된 적 없음. [확인]
- consultation_settlements.id=33: session_id=동일, consultant_id=13, revenue_p=50000,
  commission_pct=20, payout_p=38680, status=pending. [확인]
- 원장 전체 31건 중 revenue_p<>credits_charged 미스매치 정확히 1건(=id=33). [확인]

### 집계 오염(코드 근거)
consultation_service.py 의 3개 집계가 정산원장을 세션상태 조인 없이 그대로 합산:
- _stats_by_consultant (317-347) → admin_list(350) 관리자 상담사관리 뷰
- settlement_totals (398-411) 관리자 정산 합계
- consultant_earnings (414+) 상담사 '내 수익'
세션 accepted_at/credits_charged 로 거르지 않음 → 유령행 전액 계상.
라이브 수치: 플랫폼 total_revenue=1,442,000(유령 50,000 포함 → 실제 1,392,000),
pending_payout=1,115,532(유령 38,680 포함 → 실제 1,076,852).
consultant13 지급대기 +38,680, 관리자 매출 +50,000 허위 계상. [확인]

### 원인/타임라인(claim 서술 검증)
- D4 가드(session_service.py:233 미수락→cancelled, 265-267 revenue<=0 return)는
  커밋 69ec58ad(2026-07-08 19:18:11 KST)에서 도입.
- 유령행 created_at=2026-07-08 06:40:54 = D4 커밋 약 12시간 이전.
  → pre-D4(price_p 폴백) 코드가 만든 잔존 데이터. 현행 코드로는 재생성 불가(가드 확인).
- ConsultationSettlement 인스턴스화는 코드 전체에서 단 1곳(session_service.py:279),
  end_session→_ensure_settlement 경로뿐. 현행 경로는 유령행 생성 안 함. [확인]
- 정리 마이그레이션/청소 없음(0013은 테이블 생성 마이그레이션). settlement_service.py 파일 없음. [확인]

### 심각도 하향 근거(medium→low)
- 코드 결함이 아니라 이미 수정된(D4) 코드가 남긴 1건 잔존 데이터(청소 대상).
- 전부 테스트 DB(오늘자 31건 전부 pending, settled 0건; test 계정 yeon/user91).
- 정산 'settle'(consultation.py:1058, service:464)은 status만 pending→settled 로
  플립 + settled_at 기록. 실제 크레딧 이동/외부지급 API 없음(정산표시만).
  → 자동 자금유출 아님. 관리자가 부풀린 화면 보고 오프라인 과지급할 위험(운영상)만.
- 판매·이관 전 1행 DELETE 청소 + 집계에 세션결제 검증(방어) 추가 권고. 유효한 위생 항목이나
  medium 은 운영 위험을 다소 과장. → low.
