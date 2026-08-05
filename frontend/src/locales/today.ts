/** TodayPage(오늘의 운세) 문자열 카탈로그 — common.today 로 병합.
 * 일진 라벨(iljin.label)·십성(ten_god.ko/hanja)·일간(day_master)·행운색/방위/오행(lucky.*)·
 * relation.note·연간 domains(d.label) 등은 백엔드 산출값 → 그대로 렌더(백엔드 i18n 영역).
 * ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어.
 */
export const todayKo = {
  // 날짜 포맷(fmtToday) — weekdays 는 콤마 구분 7개(일요일 시작)
  date_fmt: "{{m}}월 {{d}}일 ({{w}})",
  weekdays: "일,월,화,수,목,금,토",

  // 복사/공유/PDF 직렬화(todayText)
  txt_title: "[오늘의 운세] {{date}} · 일진 {{iljin}}",
  txt_energy: "오늘의 기운: {{tg}}({{hanja}}) — 일간 {{dm}}({{stem}}) 기준",
  txt_lucky: "행운의 색 {{color}} · 행운의 방위 {{dir}} · 오늘의 오행 {{elem}}",
  txt_year_head: "[올해({{year}} {{gz}}년) 배경 흐름]",

  // 히어로
  hero_badge: "今日",
  hero_title: "오늘의 운세",
  hero_desc: "매일 바뀌는 <b>오늘 일진(日辰)</b>과 내 일간의 <b>십성·충합</b>을 규칙으로 계산해 드려요. 로그인해 두면 매일 아침 알림으로 받아볼 수 있어요. <b>무료</b>입니다.",

  // 조회 CTA
  loading: "보는 중…",
  cta: "🌅 오늘 운세 보기 (무료)",
  cta_hint: "생년월일을 입력해 주세요",
  load_fail: "오늘의 운세를 불러오지 못했어요.",

  // 결과
  iljin_badge: "일진 {{label}}",
  tengod_sub: "일간 {{dm}}({{stem}}) 기준 오늘의 기운",
  lucky_color: "🎨 행운의 색",
  lucky_dir: "🧭 행운의 방위",
  lucky_elem: "🌿 오늘의 오행",
  year_head: "올해({{year}}) 배경 흐름",
  year_head_sub: "— {{gz}}년 기준, 연중 동일",

  // PDF/상담서
  pdf_doc: "{{who}} 님의 오늘의 운세",
  pdf_person: "{{who}} 님",
  pdf_item: "{{date}} 오늘의 운세",

  // B-6 공유 카드
  card_fail: "공유 카드를 만들지 못했어요.",
  share_quota_alert: "무료 공유 횟수를 모두 사용했어요. 월 패스를 이용하면 더 많이 공유할 수 있어요.",
  share_login_alert: "공유하려면 먼저 로그인해 주세요.",
  card_filename: "오늘의운세.png",
  share_title: "오늘의 운세",
  share_desc: "오늘 일진과 나의 기운을 확인해 보세요.",
  share_fail_toast: "공유에 실패했어요. 링크 복사로 전달해 주세요.",
  link_copied: "카드 링크를 복사했어요. 원하는 곳에 붙여넣어 공유해 주세요!",
  longpress_save: "이미지를 길게 눌러 저장 후 공유해 주세요.",
  card_alt: "오늘의 운세 공유 카드",
  share_btn: "공유하기",
  save_done: "✅ 저장 완료",
  save_btn: "⤓ 저장",
  card_making: "📤 오늘 운세 공유 카드를 만들고 있어요…",
  card_make_btn: "📤 오늘 운세 공유 카드 만들기",

  // 하단 안내(사주 상담 링크)
  note: "더 깊은 풀이가 궁금하면 <chat>사주 상담</chat>에서 이어서 물어보세요.",
};

export const todayVi: typeof todayKo = {
  // 날짜 포맷 — 베트남 관례 일/월, 요일 CN(주일)·T2~T7
  date_fmt: "{{d}}/{{m}} ({{w}})",
  weekdays: "CN,T2,T3,T4,T5,T6,T7",

  // 복사/공유/PDF 직렬화
  txt_title: "[Vận hôm nay] {{date}} · nhật thần {{iljin}}",
  txt_energy: "Khí vận hôm nay: {{tg}}({{hanja}}) — theo nhật can {{dm}}({{stem}})",
  txt_lucky: "Màu may mắn {{color}} · Hướng may mắn {{dir}} · Ngũ hành hôm nay {{elem}}",
  txt_year_head: "[Dòng chảy nền năm nay ({{year}} — năm {{gz}})]",

  // 히어로
  hero_badge: "🌅",
  hero_title: "Vận hôm nay",
  hero_desc: "Tính theo quy tắc <b>nhật thần hôm nay</b> (thay đổi mỗi ngày) và <b>thập thần·xung hợp</b> với nhật can của bạn. Đăng nhập để nhận thông báo mỗi sáng. <b>Miễn phí</b>.",

  // 조회 CTA
  loading: "Đang xem…",
  cta: "🌅 Xem vận hôm nay (miễn phí)",
  cta_hint: "Vui lòng nhập ngày sinh của bạn",
  load_fail: "Không tải được vận hôm nay.",

  // 결과
  iljin_badge: "Nhật thần {{label}}",
  tengod_sub: "Khí vận hôm nay theo nhật can {{dm}}({{stem}})",
  lucky_color: "🎨 Màu may mắn",
  lucky_dir: "🧭 Hướng may mắn",
  lucky_elem: "🌿 Ngũ hành hôm nay",
  year_head: "Dòng chảy nền năm nay ({{year}})",
  year_head_sub: "— theo năm {{gz}}, giữ nguyên cả năm",

  // PDF/상담서
  pdf_doc: "Vận hôm nay của {{who}}",
  pdf_person: "{{who}}",
  pdf_item: "Vận hôm nay {{date}}",

  // B-6 공유 카드
  card_fail: "Không tạo được thẻ chia sẻ.",
  share_quota_alert: "Bạn đã dùng hết số lần chia sẻ miễn phí. Dùng gói tháng để chia sẻ được nhiều hơn.",
  share_login_alert: "Vui lòng đăng nhập trước khi chia sẻ.",
  card_filename: "van-hom-nay.png",
  share_title: "Vận hôm nay",
  share_desc: "Xem nhật thần hôm nay và khí vận của bạn.",
  share_fail_toast: "Chia sẻ thất bại. Hãy sao chép liên kết để gửi nhé.",
  link_copied: "Đã sao chép liên kết thẻ. Dán vào nơi bạn muốn để chia sẻ nhé!",
  longpress_save: "Nhấn giữ ảnh để lưu rồi chia sẻ nhé.",
  card_alt: "Thẻ chia sẻ vận hôm nay",
  share_btn: "Chia sẻ",
  save_done: "✅ Đã lưu",
  save_btn: "⤓ Lưu",
  card_making: "📤 Đang tạo thẻ chia sẻ vận hôm nay…",
  card_make_btn: "📤 Tạo thẻ chia sẻ vận hôm nay",

  // 하단 안내
  note: "Muốn luận giải sâu hơn, hãy hỏi tiếp tại <chat>Tư vấn Tứ Trụ</chat>.",
};
