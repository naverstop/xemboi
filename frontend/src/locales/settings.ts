/** SettingsPage(설정) 문자열 카탈로그 — common.settings 로 병합.
 * 사투리 라벨(DIALECTS.label)은 api.ts 데이터 상수(백엔드 값 매핑)라 별도(백엔드 i18n 영역).
 */
export const settingsKo = {
  title: "설정",
  login_required: "로그인이 필요합니다. <a>로그인</a>",
  pay_section: "결제 / 충전",
  balance_label: "보유 포인트",
  go_charge: "충전하러 가기",

  // 기본 정보(프로필)
  basic_info: "기본 정보",
  email_label: "이메일",
  nickname: "닉네임",
  saved: "저장되었습니다.",
  saving: "저장중...",
  save: "저장",

  // 답변 말투(사투리)
  dialect_title: "답변 말투(사투리)",
  dialect_desc: "상담친구가 답변할 때 사용할 말투를 선택하세요.",
  dialect_saved: "답변 말투가 변경되었습니다.",

  // 비밀번호 변경
  pw_title: "비밀번호 변경",
  pw_current_ph: "현재 비밀번호",
  pw_new_ph: "새 비밀번호",
  pw_saved: "비밀번호가 변경되었습니다.",
  changing: "변경중...",
  change: "변경",

  // 사주 프로필
  profiles_title: "사주 프로필 (가족·지인)",
  profiles_desc: "본인 외 가족·지인의 사주를 저장해 두면 상담 시작 시 빠르게 불러올 수 있습니다.",
  label_required: "이름(라벨)을 입력하세요.",
  limit_reached: "프로필은 최대 개수까지만 저장할 수 있습니다.",
  confirm_delete: "이 프로필을 삭제할까요?",
  loading: "불러오는 중...",
  empty: "저장된 프로필이 없습니다.",
  badge_default: "기본",
  lunar: "음력",
  solar: "양력",
  female: "여성",
  male: "남성",
  set_default: "기본",
  edit: "수정",
  delete: "삭제",
  label: "이름(라벨)",
  label_ph: "예: 어머니, 김친구",
  birth_date: "생년월일",
  birth_quick_ph: "숫자 8자리 예: 20080810",
  birth_time: "태어난 시각",
  leap_month: "윤달",
  default_profile: "기본 프로필",
  add: "추가",
  cancel: "취소",
  add_profile: "+ 프로필 추가",
};

export const settingsVi: typeof settingsKo = {
  title: "Cài đặt",
  login_required: "Bạn cần đăng nhập. <a>Đăng nhập</a>",
  pay_section: "Thanh toán / Nạp điểm",
  balance_label: "Điểm hiện có",
  go_charge: "Đi nạp điểm",

  // 기본 정보(프로필)
  basic_info: "Thông tin cơ bản",
  email_label: "Email",
  nickname: "Biệt danh",
  saved: "Đã lưu.",
  saving: "Đang lưu...",
  save: "Lưu",

  // 답변 말투(사투리)
  dialect_title: "Giọng điệu trả lời (phương ngữ)",
  dialect_desc: "Chọn giọng điệu mà người bạn tư vấn sẽ dùng khi trả lời.",
  dialect_saved: "Đã thay đổi giọng điệu trả lời.",

  // 비밀번호 변경
  pw_title: "Đổi mật khẩu",
  pw_current_ph: "Mật khẩu hiện tại",
  pw_new_ph: "Mật khẩu mới",
  pw_saved: "Đã đổi mật khẩu.",
  changing: "Đang đổi...",
  change: "Đổi",

  // 사주 프로필
  profiles_title: "Hồ sơ Tứ Trụ (gia đình·người quen)",
  profiles_desc: "Lưu lá số của gia đình·người quen (ngoài bạn) để nhanh chóng gọi lại khi bắt đầu tư vấn.",
  label_required: "Vui lòng nhập tên (nhãn).",
  limit_reached: "Bạn chỉ có thể lưu tối đa số hồ sơ cho phép.",
  confirm_delete: "Xóa hồ sơ này?",
  loading: "Đang tải...",
  empty: "Chưa có hồ sơ nào được lưu.",
  badge_default: "Mặc định",
  lunar: "Âm lịch",
  solar: "Dương lịch",
  female: "Nữ",
  male: "Nam",
  set_default: "Mặc định",
  edit: "Sửa",
  delete: "Xóa",
  label: "Tên (nhãn)",
  label_ph: "VD: Mẹ, bạn Nam",
  birth_date: "Ngày sinh",
  birth_quick_ph: "8 chữ số, VD: 20080810",
  birth_time: "Giờ sinh",
  leap_month: "Tháng nhuận",
  default_profile: "Hồ sơ mặc định",
  add: "Thêm",
  cancel: "Hủy",
  add_profile: "+ Thêm hồ sơ",
};
