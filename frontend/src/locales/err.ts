/** API 에러 메시지 카탈로그 — common.err 로 병합.
 * api.ts(parseError/statusFallback)가 서버 detail/코드/HTTP상태를 로케일 메시지로 치환할 때 사용.
 * ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어.
 */
export const errKo = {
  // 알려진 영어 코드 → 친화 메시지
  invalid_credentials: "이메일 또는 비밀번호가 올바르지 않습니다. 다시 확인해 주세요.",
  login_required: "로그인이 필요해요. 먼저 로그인해 주세요.",
  admin_only: "관리자 전용 기능이에요.",
  email_registered: "이미 가입된 이메일이에요. 로그인해 주세요.",
  invalid_refresh: "로그인이 만료되었어요. 다시 로그인해 주세요.",
  user_not_found: "계정을 찾을 수 없어요. 다시 로그인해 주세요.",
  share_quota: "오늘 공유 횟수를 모두 사용했어요.",
  not_your_session: "본인의 상담만 이용할 수 있어요.",
  login_to_share: "공유하려면 먼저 로그인해 주세요.",
  // HTTP 상태코드별 기본 메시지
  s401: "로그인이 필요하거나 인증이 만료되었어요. 다시 로그인해 주세요.",
  s403: "이 기능에 접근할 권한이 없어요.",
  s404: "요청한 정보를 찾을 수 없어요.",
  s409: "이미 존재하는 정보예요.",
  s429: "요청이 많아요. 잠시 후 다시 시도해 주세요.",
  s500: "서버에 일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요.",
  s_other: "요청 처리 중 오류가 발생했어요. ({{status}})",
  // FastAPI 입력 검증 오류
  validation: "입력값을 확인해 주세요: {{msgs}}",
};

export const errVi: typeof errKo = {
  invalid_credentials: "Email hoặc mật khẩu không đúng. Vui lòng kiểm tra lại.",
  login_required: "Cần đăng nhập. Vui lòng đăng nhập trước.",
  admin_only: "Tính năng chỉ dành cho quản trị.",
  email_registered: "Email đã được đăng ký. Vui lòng đăng nhập.",
  invalid_refresh: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
  user_not_found: "Không tìm thấy tài khoản. Vui lòng đăng nhập lại.",
  share_quota: "Bạn đã dùng hết số lần chia sẻ hôm nay.",
  not_your_session: "Bạn chỉ có thể dùng phiên tư vấn của chính mình.",
  login_to_share: "Vui lòng đăng nhập trước khi chia sẻ.",
  s401: "Cần đăng nhập hoặc phiên đã hết hạn. Vui lòng đăng nhập lại.",
  s403: "Bạn không có quyền truy cập tính năng này.",
  s404: "Không tìm thấy thông tin yêu cầu.",
  s409: "Thông tin đã tồn tại.",
  s429: "Có quá nhiều yêu cầu. Vui lòng thử lại sau giây lát.",
  s500: "Máy chủ đang gặp sự cố tạm thời. Vui lòng thử lại sau.",
  s_other: "Đã xảy ra lỗi khi xử lý yêu cầu. ({{status}})",
  validation: "Vui lòng kiểm tra dữ liệu nhập: {{msgs}}",
};
