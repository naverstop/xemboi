/** 게이트/PWA/진행dock/결과 페이지 공용 문자열 — common.misc 로 병합.
 * 대상: ProgressDock·DisclaimerGate·TermsGate·InstallPrompt·PaymentResultPage·OAuthSuccessPage.
 * ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어.
 * TermsGate/DisclaimerGate 의 약관 체크리스트 라벨은 auth.* 기존 키를 재사용(여기엔 없음).
 */
export const miscKo = {
  ad_label: "광고",
  biz_unset: "(운영자 설정 전)",
  // 공용(동의 게이트)
  processing: "처리 중…",
  agree_start: "동의하고 시작하기",
  gate_fail: "동의 처리에 실패했습니다. 다시 시도해 주세요.",

  // ── ProgressDock: 영상 레인 ──
  vid_title: "🎬 사주 영상 만들기",
  vid_preparing: "준비 중…",
  vid_crosssell: "기다리는 동안 다른 운세도 보실래요?",
  vid_done: "영상이 완성됐어요! 🎉",
  vid_dl_progress: "⏳ 다운로드 중… {{pct}}% · 완료될 때까지 잠시만요(다시 누르지 마세요)",
  vid_dl_btn: "⤓ 영상 다운로드",
  vid_dl_btn_busy: "⏳ 다운로드 중… {{pct}}%",
  vid_note_48h: "※ 48시간 동안만 보관되며 이후 서버에서 삭제됩니다.",
  vid_filename: "사주영상",
  vid_expired: "보관 기간이 지나 영상이 삭제되었어요.",
  vid_dl_fail: "다운로드에 실패했어요. 잠시 후 다시 시도해 주세요.",
  vid_gen_fail: "영상 생성에 실패했어요. 차감된 포인트는 자동 환불됩니다.",

  // ── ProgressDock: 생성 레인(PDF·감정서) ──
  gen_pdf_title: "📄 상담서 PDF",
  gen_pdf_open: "PDF",
  gen_report_title: "📋 종합 감정서",
  gen_report_open: "감정서",
  gen_running: "⏳ 만드는 중… {{sec}}초 경과 · 잠시만요(다시 누르지 마세요)",
  gen_open: "⤓ {{what}} 열기",
  gen_done_note: "완성됐어요 · 재생성 없이 바로 열람됩니다.",
  gen_amulet_title: "🧧 부적 발행", gen_amulet_open: "부적",
  vid_prep_progress: "⏳ 파일 준비 중… {{pct}}%", vid_retry: "다시 시도",
  vid_play: "▶ 열기(재생)", vid_btn_prep: "⏳ 준비 중… {{pct}}%",
  vid_saved_again: "✅ 저장됨 · 다시 받기", vid_save: "⤓ 다운로드(저장)",
  autoclose: "잠시 후 창이 닫힙니다 · {{sec}}초 — 계속 두려면 누르세요",
  vid_note_retention: "※ 48시간 동안만 보관되며 이후 서버에서 삭제됩니다.",
  vid_note_resave: "저장이 시작되지 않았다면 버튼을 다시 눌러 주세요.",
  save_short: "저장",
  dl_redownload_confirm: "다시 다운로드 하시겠습니까?", dl_reopen_confirm: "다시 여시겠습니까?",
  dl_opening: "⏳ 여는 중…", dl_downloading: "⏳ 다운로드 중…",
  dl_open_done: "✅ 열람 완료 · 다시 열기", dl_done: "✅ 다운로드 완료",
  gen_fail: "생성에 실패했어요. 잠시 후 다시 시도해 주세요.",

  // ── DisclaimerGate ──
  disc_aria: "면책고지 동의",
  disc_title: "⚠️ 면책고지 안내",
  disc_body:
    "본 서비스 답변에 의존하여 행한 의사결정의 결과에 대해 회사는 그 어떠한 법적 책임 및 관련 일체의 책임을 지지 않습니다.",
  disc_sub:
    "아래 <b>「동의하고 시작하기」</b>를 누르는 순간, 사용자는 본 사항에 대하여 동의한 것으로 간주합니다.",
  disc_foot: "전문(全文)은 <a>면책고지</a>에서 확인할 수 있습니다.",

  // ── TermsGate ──
  terms_aria: "약관 동의",
  terms_title: "📋 서비스 이용 약관 동의",
  terms_sub: "서비스 이용을 위해 약관 동의가 필요합니다. 필수 항목에 동의해 주세요.",
  terms_err_required: "필수 약관 3개에 모두 동의해야 합니다.",
  agree_refund: "<a>환불정책</a>에 동의합니다.",
  agree_marketing: "마케팅 정보 수신에 동의합니다.",

  // ── InstallPrompt(PWA) ──
  pwa_title: "앱으로 설치하기",
  pwa_popup_body: "홈 화면에 추가하면 더 빠르게 실행되고, 오늘의 운세 알림을 받을 수 있어요.",
  pwa_later: "나중에",
  pwa_install: "설치",
  pwa_ios_body:
    "Safari 하단의 <b>공유</b> 버튼을 누른 뒤, <b>“홈 화면에 추가”</b>를 선택하면 앱처럼 사용할 수 있어요.",
  pwa_confirm: "확인",

  // ── PaymentResultPage ──
  pay_confirming: "결제 승인 처리 중...",
  pay_missing_params: "필수 파라미터 누락",
  pay_success: "+{{credits}} {{pt}} 충전 완료. 잔액: {{balance}} {{pt}}",
  pay_processing: "처리 중",
  pay_done: "결제 완료",
  pay_failed: "결제 실패",
  pay_to_chat: "대화로",
  pay_fail_msg: "결제가 취소되었거나 실패했습니다.",
  pay_retry: "다시 시도",

  // ── OAuthSuccessPage ──
  oauth_no_token: "토큰을 찾을 수 없습니다.",
  oauth_profile_fail: "프로필 조회 실패",
  oauth_processing: "로그인 처리 중...",
};

export const miscVi: typeof miscKo = {
  ad_label: "Quảng cáo",
  biz_unset: "(chưa cấu hình)",
  processing: "Đang xử lý…",
  agree_start: "Đồng ý và bắt đầu",
  gate_fail: "Xử lý đồng ý thất bại. Vui lòng thử lại.",

  vid_title: "🎬 Tạo video Tứ Trụ",
  vid_preparing: "Đang chuẩn bị…",
  vid_crosssell: "Trong lúc chờ, bạn xem thêm nội dung khác nhé?",
  vid_done: "Video đã hoàn thành! 🎉",
  vid_dl_progress: "⏳ Đang tải… {{pct}}% · Vui lòng đợi đến khi xong (đừng nhấn lại)",
  vid_dl_btn: "⤓ Tải video",
  vid_dl_btn_busy: "⏳ Đang tải… {{pct}}%",
  vid_note_48h: "※ Chỉ lưu trong 48 giờ, sau đó sẽ bị xóa khỏi máy chủ.",
  vid_filename: "Video Tứ Trụ",
  vid_expired: "Video đã bị xóa do quá thời hạn lưu.",
  vid_dl_fail: "Tải xuống thất bại. Vui lòng thử lại sau.",
  vid_gen_fail: "Tạo video thất bại. Điểm đã trừ sẽ được hoàn lại tự động.",

  gen_pdf_title: "📄 PDF tư vấn",
  gen_pdf_open: "PDF",
  gen_report_title: "📋 Bản luận giải tổng hợp",
  gen_report_open: "Bản luận giải",
  gen_running: "⏳ Đang tạo… đã {{sec}} giây · Vui lòng đợi (đừng nhấn lại)",
  gen_open: "⤓ Mở {{what}}",
  gen_done_note: "Đã xong · Mở xem ngay, không tạo lại.",
  gen_amulet_title: "🧧 Phát hành bùa hộ mệnh", gen_amulet_open: "Bùa hộ mệnh",
  vid_prep_progress: "⏳ Đang chuẩn bị tệp… {{pct}}%", vid_retry: "Thử lại",
  vid_play: "▶ Mở (phát)", vid_btn_prep: "⏳ Đang chuẩn bị… {{pct}}%",
  vid_saved_again: "✅ Đã lưu · Tải lại", vid_save: "⤓ Tải xuống (lưu)",
  autoclose: "Cửa sổ sẽ tự đóng sau {{sec}} giây — bấm để giữ lại",
  vid_note_retention: "※ Video chỉ lưu 48 giờ, sau đó bị xóa khỏi máy chủ.",
  vid_note_resave: "Nếu chưa bắt đầu lưu, hãy bấm nút lần nữa.",
  save_short: "Lưu",
  dl_redownload_confirm: "Tải xuống lại?", dl_reopen_confirm: "Mở lại?",
  dl_opening: "⏳ Đang mở…", dl_downloading: "⏳ Đang tải…",
  dl_open_done: "✅ Đã mở · Mở lại", dl_done: "✅ Đã tải xuống",
  gen_fail: "Tạo thất bại. Vui lòng thử lại sau.",

  disc_aria: "Đồng ý tuyên bố miễn trừ",
  disc_title: "⚠️ Thông báo miễn trừ trách nhiệm",
  disc_body:
    "Công ty không chịu bất kỳ trách nhiệm pháp lý hay trách nhiệm liên quan nào đối với hậu quả của những quyết định mà bạn đưa ra khi dựa vào câu trả lời của dịch vụ này.",
  disc_sub:
    "Ngay khi nhấn <b>「Đồng ý và bắt đầu」</b> bên dưới, bạn được xem là đã đồng ý với nội dung này.",
  disc_foot: "Bạn có thể xem <a>toàn văn tuyên bố miễn trừ</a> tại đây.",

  terms_aria: "Đồng ý điều khoản",
  terms_title: "📋 Đồng ý điều khoản dịch vụ",
  terms_sub: "Cần đồng ý điều khoản để sử dụng dịch vụ. Vui lòng đồng ý các mục bắt buộc.",
  terms_err_required: "Bạn phải đồng ý cả 3 điều khoản bắt buộc.",
  agree_refund: "Đồng ý <a>Chính sách hoàn tiền</a>.",
  agree_marketing: "Đồng ý nhận thông tin tiếp thị.",

  pwa_title: "Cài đặt ứng dụng",
  pwa_popup_body: "Thêm vào màn hình chính để mở nhanh hơn và nhận thông báo vận hôm nay.",
  pwa_later: "Để sau",
  pwa_install: "Cài đặt",
  pwa_ios_body:
    "Nhấn nút <b>Chia sẻ</b> ở dưới cùng Safari, rồi chọn <b>“Thêm vào màn hình chính”</b> để dùng như một ứng dụng.",
  pwa_confirm: "Đã hiểu",

  pay_confirming: "Đang xử lý phê duyệt thanh toán...",
  pay_missing_params: "Thiếu tham số bắt buộc",
  pay_success: "+{{credits}} {{pt}} đã nạp. Số dư: {{balance}} {{pt}}",
  pay_processing: "Đang xử lý",
  pay_done: "Thanh toán thành công",
  pay_failed: "Thanh toán thất bại",
  pay_to_chat: "Vào tư vấn",
  pay_fail_msg: "Thanh toán đã bị hủy hoặc thất bại.",
  pay_retry: "Thử lại",

  oauth_no_token: "Không tìm thấy token.",
  oauth_profile_fail: "Không lấy được hồ sơ.",
  oauth_processing: "Đang xử lý đăng nhập...",
};
