/** AmuletPage(부적 발행) 문자열 카탈로그 — common.amulet 로 병합.
 * 부적명(amulet.name/hanja)·오행/오방(element/obang)·삼재(samjae)·purpose_label·reasons·disclaimer 는
 * 백엔드 산출값 → 그대로 렌더(백엔드 i18n 영역). ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어.
 */
export const amuletKo = {
  // 목적 6종(PURPOSES key 별 라벨 p_* / 설명 pd_*)
  p_wealth: "재물", pd_wealth: "금전·재수의 기운을 북돋아요",
  p_love: "애정", pd_love: "인연·화합의 기운을 열어요",
  p_exam: "합격·시험", pd_exam: "학업·시험 성취를 기원해요",
  p_health: "건강", pd_health: "무병장수의 기운을 지켜요",
  p_protect: "액막이", pd_protect: "삼재·액운을 막아내요",
  p_biz: "개업·사업", pd_biz: "사업 번창의 문을 열어요",

  // 지난 결과 서랍
  past_label: "내 부적",
  past_empty: "아직 발행한 부적이 없어요.",
  past_note: "🕰 발행한 부적은 언제든 다시 볼 수 있어요 — 재열람은 포인트가 차감되지 않아요.",
  past_title: "{{label}} 부적",
  fallback_label: "부적",

  // 발행 사전검사·확인
  alert_pick_purpose: "부적의 목적을 먼저 골라 주세요!\n\n위의 ①번에서 재물·애정·액막이 등 원하는 목적을 선택하면 발행할 수 있어요.",
  alert_birth: "생년월일을 입력해 주세요.",
  err_login_only: "부적 발행은 로그인 후 이용할 수 있어요.",
  need_charge: "부적 발행에는 {{cost}}P가 필요해요. 충전하면 바로 발행해 드려요.",
  confirm_title: "{{label}} 부적을 발행할까요?",
  confirm_pass: "· 플러스 패스 무료 발행권을 사용합니다 (차감 없음)",
  confirm_cost: "· {{cost}}P가 차감됩니다 (발행 실패 시 무과금)",
  confirm_basis: "· 내 사주와 올해 기운을 규칙으로 읽어 발행 근거를 함께 드려요",
  confirm_disc: "· 전통 문화 콘텐츠(오락 목적)로, 특정 효험을 보장하지 않아요",

  // 발행 실패
  gen_fail: "부적 발행에 실패했어요.",
  fail_retry: "부적 발행에 실패했어요. 잠시 후 다시 시도해 주세요.",

  // 히어로
  hero_badge: "符籍",
  hero_title: "부적 발행",
  hero_desc: "내 사주의 <b>용신(보강 기운)</b>과 올해의 <b>충·형·해·삼재</b>를 정해진 규칙으로 읽어, 목적에 맞는 부적을 발행해 드려요. 발행 근거를 함께 보여 드립니다.",
  hero_free: "이번 주기 무료 발행 {{n}}회 남음(플러스 패스)",
  hero_cost: "<b>{{cost}}P</b> · 실패 시 무과금.",

  // 단계·폼
  step1: "1. 목적을 골라 주세요",
  step2: "2. 생년월일을 확인해 주세요",
  member_only: "🔒 부적 발행은 <b>회원 전용</b>이에요. 로그인하면 저장된 내 사주로 바로 발행할 수 있어요.",

  // CTA
  busy: "발행 중…",
  cta_free: "🧧 부적 발행 (패스 무료 1회)",
  cta_paid: "🧧 부적 발행 ({{cost}}P)",
  hint_pick: "① 위에서 부적의 목적을 먼저 골라 주세요",
  hint_birth: "생년월일을 입력해 주세요",

  // 결과
  receipt: "✓ 부적 발행 {{n}} P 차감됨",
  img_alt: "{{name}} 부적",
  boost_label: "보강 기운",
  year_label: "올해",
  reasons_title: "발행 근거 (규칙 기반)",
  save_done: "✅ 저장 완료",
  save_btn: "⤓ 부적 저장 (PNG)",

  // 복사/공유 직렬화·PDF
  txt_head: "{{name}}({{hanja}}) 부적 — {{purpose}}",
  txt_boost: "보강 기운: {{elem}} {{obang}}",
  txt_year: " · 올해 {{samjae}}",
  txt_reasons_head: "[발행 근거]",
  pdf_doc: "{{who}} 님의 {{purpose}} 부적",
  pdf_person: "{{who}} 님",
  pdf_item: "부적 발행 ({{name}})",
};

export const amuletVi: typeof amuletKo = {
  // 목적 6종
  p_wealth: "Tài lộc", pd_wealth: "Bồi đắp khí vận tiền tài·may mắn",
  p_love: "Tình duyên", pd_love: "Mở khí vận nhân duyên·hòa hợp",
  p_exam: "Thi cử·đỗ đạt", pd_exam: "Cầu thành tựu học hành·thi cử",
  p_health: "Sức khỏe", pd_health: "Giữ khí vận khỏe mạnh sống lâu",
  p_protect: "Trừ tà giải hạn", pd_protect: "Ngăn tam tai·vận xui",
  p_biz: "Khai trương·kinh doanh", pd_biz: "Mở cánh cửa kinh doanh phát đạt",

  // 지난 결과 서랍
  past_label: "Bùa của tôi",
  past_empty: "Bạn chưa phát hành lá bùa nào.",
  past_note: "🕰 Bùa đã phát hành có thể xem lại bất cứ lúc nào — xem lại không trừ điểm.",
  past_title: "Bùa {{label}}",
  fallback_label: "hộ mệnh",

  // 발행 사전검사·확인
  alert_pick_purpose: "Vui lòng chọn mục đích của lá bùa trước!\n\nChọn mục đích bạn muốn như tài lộc·tình duyên·trừ tà giải hạn ở mục ① phía trên là có thể phát hành.",
  alert_birth: "Vui lòng nhập ngày sinh.",
  err_login_only: "Phát hành bùa chỉ dùng được sau khi đăng nhập.",
  need_charge: "Phát hành bùa cần {{cost}} điểm. Nạp điểm là phát hành được ngay.",
  confirm_title: "Phát hành bùa {{label}} nhé?",
  confirm_pass: "· Dùng lượt phát hành miễn phí của Gói Plus (không trừ điểm)",
  confirm_cost: "· Sẽ trừ {{cost}} điểm (không mất điểm nếu phát hành thất bại)",
  confirm_basis: "· Đọc lá số của bạn và khí vận năm nay theo quy tắc, kèm căn cứ phát hành",
  confirm_disc: "· Là nội dung văn hóa truyền thống (mục đích giải trí), không bảo đảm hiệu nghiệm cụ thể",

  // 발행 실패
  gen_fail: "Phát hành bùa thất bại.",
  fail_retry: "Phát hành bùa thất bại. Vui lòng thử lại sau.",

  // 히어로
  hero_badge: "🧧",
  hero_title: "Phát hành bùa hộ mệnh",
  hero_desc: "Đọc <b>dụng thần (khí bổ trợ)</b> trong lá số của bạn và <b>xung·hình·hại·tam tai</b> của năm nay theo quy tắc định sẵn để phát hành lá bùa đúng mục đích. Kèm theo căn cứ phát hành.",
  hero_free: "Kỳ này còn {{n}} lượt phát hành miễn phí (Gói Plus)",
  hero_cost: "<b>{{cost}} điểm</b> · thất bại không mất điểm.",

  // 단계·폼
  step1: "1. Chọn mục đích",
  step2: "2. Kiểm tra ngày sinh",
  member_only: "🔒 Phát hành bùa <b>chỉ dành cho thành viên</b>. Đăng nhập để phát hành ngay với lá số đã lưu của bạn.",

  // CTA
  busy: "Đang phát hành…",
  cta_free: "🧧 Phát hành bùa (1 lượt miễn phí của gói)",
  cta_paid: "🧧 Phát hành bùa ({{cost}} điểm)",
  hint_pick: "① Vui lòng chọn mục đích của lá bùa ở phía trên trước",
  hint_birth: "Vui lòng nhập ngày sinh",

  // 결과
  receipt: "✓ Phát hành bùa — đã trừ {{n}} điểm",
  img_alt: "Bùa {{name}}",
  boost_label: "Khí bổ trợ",
  year_label: "năm nay",
  reasons_title: "Căn cứ phát hành (theo quy tắc)",
  save_done: "✅ Đã lưu",
  save_btn: "⤓ Lưu bùa (PNG)",

  // 복사/공유 직렬화·PDF
  txt_head: "Bùa {{name}} ({{hanja}}) — {{purpose}}",
  txt_boost: "Khí bổ trợ: {{elem}} {{obang}}",
  txt_year: " · năm nay {{samjae}}",
  txt_reasons_head: "[Căn cứ phát hành]",
  pdf_doc: "Bùa {{purpose}} của {{who}}",
  pdf_person: "{{who}}",
  pdf_item: "Phát hành bùa ({{name}})",
};
