# 4/7 외부LLM 국외이전 게이팅·가명화 + 답변 품질 회귀 (READ-ONLY 재검증)

## 결론: 심화게이팅 정상 / 가명화 정상(타로 1개 예외) / 폴백 기본 false 정상 / 6메뉴 회귀 정상

### DEFECT (low)
- 타로 심화(Claude) 외부전송 경로가 `_pseudonymize_for_transfer` 미적용.
  - external_llm.py:89,390 만 가명화 적용(사주/궁합/택일·작명 refine·generate).
  - 타로: tarot_service.py:345-350(_tarot_claude_refine), 353-358(_tarot_generate_fallback) → 318-336(_tarot_claude_call) 가 user_block 원문 그대로 Claude 전송.
  - 영향: 국외이전 동의(opt_in=True) 회원이 타로 질문에 정확 나이('34세')를 적으면 연령대('30대')로 일반화 안 되고 Anthropic(미국)에 원문 전송. 사주/궁합/택일/작명은 가명화됨(불일치).

### PASSED
- 심화 게이팅: chat_service:3131 / compat:355 / tool:521 / tarot:506 모두 `depth=="deep" ... and overseas_transfer_opt_in` 게이트. 라이브(uid95 opt_in=False, 전·중·후 모두 False) 심화 사주챗 → refine='내부 보강(qwen)'만, Claude 미실행.
- 가명화 함수: '34세'→'30대','34살'→'30대'; '21세기'·'세대'·'5세'·'3세' 보존. 라이브 refine 페이로드 '34세 남성'→'30대 남성' 확인, Claude 정상 1101자.
- 폴백 기본 false: DEFAULTS·DB effective 모두 False. external_fallback_answer allow_overseas 기본 False. 폴백 3경로(chat:2894/compat:423/tool:576) opt_in AND 설정 이중게이트.
- 회귀(암호화 무손상): create_session 명식 정상 산출(庚午·辛巳·庚辰·庚辰 등 전 필드). 사주챗976·종합984(성격/육친/건강)·궁합1645·타로2122 전부 200, 5xx/빈응답/중국어드리프트 없음. 택일 결정적 날짜 정상. 작명 40후보 부적합한자(賭矢到鍍) 0(稻 등 길한 도-한자). 차감 프리미엄 각 10000P 일관.

### NOTES
- 동시 실행중인 다른 재검증 에이전트가 uid49 opt_in을 일시 True 토글(첫 inproc True 포착→이후 False 복귀). 게이트 버그 아님.
- chat_service.py:2556 `_deep_refine` 데드코드(호출부 없음). 사용 시 opt_in 게이트 없이 refine 호출 위험 → 제거/방어 권장.
- 사주/궁합 qwen 보강 출력에 마크다운(###,**) 잔존(_REFINE_SYSTEM 줄글 지시 위반). 타로는 _strip_markdown로 정리됨. 기존 포맷 편차(암호화/게이팅 회귀 아님).
