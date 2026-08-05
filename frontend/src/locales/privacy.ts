/** PrivacyNotice(개인정보 공통 고지) 문자열 카탈로그 — common.privacy 로 병합.
 * <legal> 는 /legal/privacy 링크, <b> 는 강조 — <Trans components> 로 배선.
 * ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어(현지 개인정보 보호 규정 표현).
 */
export const privacyKo = {
  // 무저장 화면(스낵 테스트 등)
  nostore: "🔒 입력하신 생년월일 등은 <b>개인정보보호법</b>에 따라 안전하게 처리되며, <b>이 결과는 별도로 저장하지 않습니다.</b> 저장된 사주 프로필은 약관에 따라 관리·파기됩니다. <legal>개인정보처리방침</legal>에서 자세히 확인하실 수 있어요.",
  // 일반 고지({{what}}=대상 데이터, {{period}}=보관기간)
  body: "🔒 입력하신 {{what}} 등 개인정보는 <b>개인정보보호법</b>에 따라 안전하게 처리·암호화되며, <b>{{period}}</b>이 지나면 자동으로 완전 파기됩니다. 회원 탈퇴 시에는 즉시 파기됩니다. <legal>개인정보처리방침</legal>에서 자세히 확인하실 수 있어요.",
  // variant 별 대상 데이터
  what_consult: "질문·대화·사주 명식",
  what_tool: "생년월일·이름 등 입력정보와 결과",
  what_answer: "생년월일·질문·답변",
  // 보관기간
  period_consult: "상담 종료 후 7일",
  period_default: "약관에서 정한 보관기간",
};

export const privacyVi: typeof privacyKo = {
  // 무저장 화면
  nostore: "🔒 Ngày sinh v.v. bạn nhập được xử lý an toàn theo <b>quy định về bảo vệ dữ liệu cá nhân</b>, và <b>kết quả này không được lưu riêng.</b> Hồ sơ lá số đã lưu được quản lý·hủy theo điều khoản. Xem chi tiết tại <legal>Chính sách quyền riêng tư</legal>.",
  // 일반 고지
  body: "🔒 Thông tin cá nhân bạn nhập ({{what}}) được xử lý·mã hóa an toàn theo <b>quy định về bảo vệ dữ liệu cá nhân</b>, và sẽ tự động hủy hoàn toàn khi hết <b>{{period}}</b>. Khi xóa tài khoản, dữ liệu bị hủy ngay lập tức. Xem chi tiết tại <legal>Chính sách quyền riêng tư</legal>.",
  // variant 별 대상 데이터
  what_consult: "câu hỏi·hội thoại·lá số",
  what_tool: "thông tin nhập như ngày sinh·họ tên và kết quả",
  what_answer: "ngày sinh·câu hỏi·câu trả lời",
  // 보관기간
  period_consult: "7 ngày sau khi kết thúc tư vấn",
  period_default: "thời hạn lưu trữ quy định trong điều khoản",
};
