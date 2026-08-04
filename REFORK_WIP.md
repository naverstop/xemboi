# 신규 화면 vi 게이팅 잔여 목록 (재분기 자체는 2026-08-05 main 머지·push 완료 — 85bb530)
아래 '후속' 항목만 남음. 이 파일은 신규 화면 vi 완료 시 삭제.

## PDF 전수감사 잔여(2026-08-05, 감사 w2xkmk9n7 — 심각·high 전부 수정완료, 아래는 med/low 후속)
- AnswerActions 공유 신형 플로우 문구 다수 KO(한도 alert·카카오 카드·메일 폼 등 — :225·310·356·562-597) → answer.* 키화
- email PDF 본문/제목 vi 문구(백엔드 분기 지점 마련됨 — 문구 자체 vi 작성)
- Stable 고스트 폭 재적용 + KO 상수 정리(AnswerActions:22-40)
- 신규화면 3종(부적·달력·오늘) PDF 메타 키 — 아래 vi 게이팅과 함께
- [사용자 결정 회부] 공유 채널: 카카오를 vi에서 숨길지 Zalo로 대체할지

## 우선순위(사용자 가시순)
1. PrivacyNotice(전 도구 페이지 상단 🔒 안내) 2. TodayPage(오늘의 운세) 3. AmuletPage(부적)
4. PaymentsPage 내부(패스 카드·포인트 원장 표) 5. InstallPrompt 설치가이드 본문 6. ReviewsPage/ReviewStrip 라벨
7. CalendarPage 8. SnackPage 9. TaekilPage rule_note/점수줄/PersonHd 10. TarotPage 세션리스트/스프레드힌트
11. ConsultationOverlay 예약·사업자 카드 12. ChargeModal EntryConfirmModal(ENTRY_MENU_LABEL/DESC→entryLabel/i18n)
13. ConsultantConsolePage 온보딩·수익탭 14. AnswerActions 영상/공유 신규 문구 15. 명령: 한국어 스캔 = 각 페이지에서
treeWalker [가-힣] 가시노드 카운트(이 세션 방식). DB 데이터(리뷰 내용·사업자값)는 제외.

# (아카이브) refork 진행 기록

## 전략(사용자 승인 A)
saju/main(=5f3b687e) 최신 스냅숏 위에 xemboi vi 작업을 재적용. 제외: 작명·아호·개명·신년운세·꿈해몽(프론트 노출만 제거, 백엔드 유지).
커밋: 462c29c(스냅숏+제외) → 64199b5(VN 인프라 10파일 복원). 이후 작업트리에서 스쿼시 오버레이 진행 중(아직 미커밋).

## 방식: 스쿼시 오버레이(24커밋 순차재생 아님)
- xemboi 전용 34파일: `git checkout c3b2185 -- <files>` 통째 복원 완료(locales/i18n/money/fonts/VN zodiac/브랜딩 에셋).
- 공유 72파일: 파일당 1회 3-way(`git merge-file`, base=e8047b0, ours=saju, theirs=c3b2185=vi최종). LF 정규화 필수(CRLF면 전체충돌).
  22개 자동병합 성공. 44개 수동 — 아래 진행.

## 해결 원칙
- saju 신로직/신구조 수용 + vi 라벨(tr()) 재적용. 색은 민트(#0d9488/#1fbfa8/#0b7d73), 파랑(#0496d8 계열) 금지.
- locale 스레딩(get_locale, locale= 인자)은 항상 보존. import는 합집합.
- 신규 KO 문구 → misc/consult 카탈로그에 키 추가(ko+vi 동시). 이미 추가: misc.gen_amulet_*, vid_prep_progress/vid_retry/vid_play/vid_btn_prep/vid_saved_again/vid_save/autoclose/vid_note_retention/vid_note_resave/save_short, consult.rb_save.

## 수동 44 중 완료(26)
LandingPage(1), api.ts, sw.js(캐시 xemboi-shell-v70), saju/compatibility.py(반합 len==2 가드+vi독음), api/compatibility.py,
DisclaimerGate, ConsultationReportButton(DownloadGuard+tr), chat_service(allow_overseas+locale), api/tools(합집합), api/saju, api/pdf,
index.html(VN SEO/OG/JSON-LD/seo-hero 전면 vi·민트, GSC토큰 제거), LoginForm, BirthFields, PaymentResultPage, SupportPage,
entryFee.ts(entryLabel+VND폴백+LABEL/DESC 유지+confirmEntry 제거), ConsultantConsolePage(saju 온보딩·알림 로직+vi 로딩),
SajuChart(메트릭스+독음, wxArr ko·el 겸용), MyeongriWheel(메달리온+vi독음·VN띠), ProgressDock(saju 구조 전면 tr화),
settings_service(VND+saju 신키 VND 환산: review 5000/amulet 39000/pass 39000·99000/sinnyeon 99000), external_llm(_sys_for(_refine_system(locale), rag)),
styles.css(saju 구조 민트화+vi VN블록, 전역 파랑 53건→민트 0잔존).

## 백엔드 재병합(빈티지 base) 진행 — 완료: constants·api 6종·main·config·settings(VND재적용)·external_llm·
chat_service(23/23: compose+vi분기·_draft_model 배선·refine 결합·R8 saju백스톱정책)·compat_service·
api/consultation(로케일 상담서+saju CAS)·consultation_session_service(락+locale, end_session 시그니처 union)
## ★백엔드 100% 완료·게이트 그린(2026-08-04): 충돌 0·py_compile 0에러·import OK·
pytest 54 passed(정확도 37+택일 ppo/ppo2/schools+월간지). 수복 내역:
- pillars: saju 3튜플 _adjust_time(진태양=시주 전용·일주 경계 보호)+vi 로케일 분기 결합, compute_pillars 동기+음력 클램프
- taekil: DayScore.reason 복원·_PERSP_LABEL P키 추가·relations/gwanbeop import 복원
- chat_service: _upcoming_months saju판(당월 포함)으로 교체 — vi 구버전이 조용히 이긴 사례(동종 주의)
- 이스케이프 사고 교정: 문자열 내 실개행("

"이 개행으로) — chat/tarot 3곳
- 마커 오인 주의: 정규식은 반드시 ^앵커(^<<<<<<< saju-main$ 등) — ====구분선 끝 7개 '='를 마커로 오인해 tarot 재병합했음
- 테스트 적법 갱신: vi 모델 가정(exaone→qwen3)·_adjust_time 3튜플 헬퍼·fake_persist locale
## 프론트 잔여(첫 병합분 유효) — 같은 원칙
InstallPrompt(3) FollowupBilling(3) ExplainChat(3) ChargeModal(4) PaymentsPage(5) ConsultationProvider(5)
compat_service(5) api/consultation(5) AnswerActions(6) tool_service(6) consultation_session_service(6)
CompatibilityPage(7) ConsultationOverlay(7) TarotPage(8) SettingsPage(8) tarot_service(8) taekil.py(8)
App.tsx(9) TaekilPage(10) ChatPage(15)
충돌 마커: `<<<<<<< saju-main` / `>>>>>>> vi-final`. 보기: awk '/^<<<<<<< /{c=1} c{print NR": "$0} /^>>>>>>> /{c=0}' <file>

## 이후 게이트(전 파일 해결 후)
1) cd frontend && npx tsc -b --force && npm run build
2) 백엔드 import: D:\saju_agent\.venv\Scripts\python.exe -c "import backend.app.main" (PYTHONPATH=D:\xemboi, CWD=D:\xemboi)
3) pytest backend/tests/test_saju_accuracy.py (26) + test_vietnam_locale.py
4) 파랑/한자/원화 grep 스윕 → 5) 프리뷰 vi 화면검증(landing/chat/compat/taekil/login, 375+1280)
6) 신규 화면(오늘운세·부적·리뷰·달력·스낵·초대·공유) vi 게이팅은 별도 후속 단계
7) 커밋 "reapply: vi 오버레이 스쿼시 재적용" → 검증 후 main 머지+push, git remote remove saju

## ★★ 중대 교정(2026-08-04 발견): base=e8047b0 는 잘못 — init에 pre-fork vi가 배어 있어
3-way가 vi를 'saju측 삭제'로 오판·조용히 제거함(chat_service SYSTEM_PROMPT_VI·deps.get_locale·config default_locale·
pillars 105·chat_dto/types locale·main.py 부트스트랩 전멸 확인). **백엔드는 base=saju 빈티지 blob(theirs와 최대 유사 saju 역사 blob),
ours=64199b5 시점 순수 saju, theirs=c3b2185 로 전면 재병합**. 프론트는 vi가 24커밋 산물이라 기존 해결 유효(재작업 불필요).
재병합 대상: 72중 backend 22개 + 엔진 6(constants/pillars/types/chat_dto/deps/main.py). 이때 이미 해결한 백엔드 수동분
(chat_service 2건·api 4파일·compat 예정분·settings·external_llm·saju/compatibility)은 같은 충돌이 재출현하므로 위 '완료' 기록대로 재적용.

## 알려진 후속(커밋 전 확인)
- ENTRY_MENU_LABEL/DESC 아직 KO(ChargeModal 커스텀 입장모달이 사용) → ChargeModal 해결 시 entryLabel()/i18n 배선
- ConsultantConsolePage 알림 title 등 KO 일부(콘솔=상담사 화면, 후속 vi)
- misc.disc_body ko 값이 saju 신문안과 다름(구버전) — ko 카탈로그 문안 갱신 후속
- SajuChart render의 wxArr/now/vi 사용처 tsc로 확인
