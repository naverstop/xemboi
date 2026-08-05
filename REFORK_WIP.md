# 신규 화면 vi 게이팅 잔여 목록 (재분기 자체는 2026-08-05 main 머지·push 완료 — 85bb530)

## ★★ 프론트 전 화면 vi 로컬라이즈 완료(2026-08-05, 브랜치 claude/hungry-hawking-72d1cd)
아래 '우선순위 1~15' + PDF 전수감사 med/low 프론트 항목 **전부 완료**. 병렬 서브에이전트 9종으로 화면별 분담 처리.
- **신설 카탈로그 11종**: today·fcal·amulet·privacy·snack·reviews·invite·partner·payx·install·libx (i18n.ts 등록 완료, `<ns>Vi: typeof <ns>Ko` 타입으로 ko/vi 키쌍 완전성 보장).
- **기존 카탈로그 확장**: chat·compat·settings·err·taekil·tarot·chart·birth·answer·misc·consult·explain.
- **언어 전환 UX 신규**: ① LanguageSwitch를 App.tsx `.app-content` 좌상단 + LoginPage(auth 셸 밖 단독) 양쪽 배선(국기 SVG 포함, active=민트 #0d9488). ② i18n `languageChanged`→`<html lang>` 동기화(index.html 정적 lang 보정). ③ 브라우저 언어 자동감지는 기존 languagedetector(localStorage saju_lang→navigator→기본 vi) 활용. ④ 셸 사이드바 하드코딩 6곳(입점/설정/상담사/업로드/추세/관리자)→tr(nav.*).
- **package.json**: i18next·i18next-browser-languagedetector·react-i18next 명시(누락 상태였음).
- **게이트 그린**: npm run build(tsc -b + vite) exit 0 / 브라우저 양방향 검증(dev :5199, saju_lang 토글): vi 선택 시 전 사용자화면(랜딩·오늘·달력·궁합·택일·부적·타로·리뷰·결제·고객센터·설정·로그인·입점신청) 가시 한글 0(스위치 '한국어' 라벨 제외) / ko 선택 시 vi 0(스위치 라벨·VND 통화 đ·VN 지역명 제외=빌드 고정, 정상) / i18n missing-key 경고 0·콘솔 에러 0 / navigator=ko→한국어 자동선택 확인.
- **데드코드 제거**: AnswerActions의 미사용 `Stable`/`*_LABELS` 상수(참조 0 grep 확인) 삭제.

## 남은 잔여(프론트 아님 / 운영자 판단)
- **백엔드 i18n(별도 작업)**: `/api/snack` 테스트 카드 제목·부제가 ko 고정(Accept-Language:vi에도 ko 반환) → 백엔드 스낵 콘텐츠 로케일화 필요. 그 외 백엔드 산출값(명식 iljin/ten_god/ganzhi·amulet 라벨·grade 등)은 기존과 동일하게 백엔드 i18n 영역.
- **관리자 백오피스 3화면 미처리(의도)**: AdminPage(KO 601)·TrendPage(78)·UploadsPage(90) — role=admin(운영자 본인) 전용, 일반/상담사 비노출이라 우선순위 최하. 필요 시 후속.
- **TTS 보이스**: tts.ts는 speak(text, lang) 확장됨(vi→vi-VN). ConsultationProvider 입장멘트도 i18n.language 분기 적용됨.
- **stash 사고 잔재**: 병렬 작업 중 한 에이전트의 `git stash` 오작동으로 stash@{0} 잔존(pop 금지 — 현 워킹트리와 충돌). 현 트리는 게이트 전부 그린이라 완전본. 백업: scratchpad\stash_recovery\. 불필요하면 운영자가 `git stash drop` 판단.
- vi 원어민 검수(사주 전문용어 자연스러움)는 기존 카탈로그와 동일 전제.

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
