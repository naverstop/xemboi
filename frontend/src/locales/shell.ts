/** 전역 셸(App.tsx) 문자열 카탈로그 — common.shell 로 병합.
 * 사이드바·테마토글·타로 바로가기·푸터(사업자 정보/면책)·유휴 자동로그아웃 모달·
 * 로그아웃/탈퇴 confirm·prompt·alert 등 전 화면 공통 크롬 문구.
 * 브랜드/네비/포인트단위·결제 관련은 기존 키(brand·nav.*·theme.*·pay.*·consult.*·legal.*) 재사용.
 * 사업자 정보 값(대표명·번호 등)은 백엔드/관리자 입력값이라 여기선 '라벨'만 담는다.
 */
export const shellKo = {
  // 사이드바 크롬
  menu: "메뉴",
  brand_home: "메인으로",
  sidebar_recent: "최근 상담",
  sidebar_empty: "아직 상담이 없어요",
  session_delete: "삭제",
  session_delete_confirm: "이 상담을 삭제할까요?",
  theme_toggle: "테마 전환",

  // 타로 바로가기
  tarot_shortcut_title: "타로 리딩 — 카드가 전하는 이야기",
  tarot_shortcut_aria: "타로 리딩 보러가기",

  // 푸터 — 사업자 정보 라벨(전자상거래법)
  biz_ceo: "대표",
  biz_reg_no: "사업자등록번호",
  biz_mailorder: "통신판매업 신고",
  biz_mailorder_pending: "준비 중",
  biz_tel: "고객센터",
  biz_hours: "운영시간",
  biz_email: "이메일",
  biz_privacy_officer: "개인정보보호책임자",
  biz_hosting: "호스팅",
  footer_note: "본 서비스 응답은 학습 자료 기반 참고용입니다. 의료·법률·투자 자문이 아닙니다.",

  // 유휴 자동 로그아웃 모달
  idle_aria: "유휴 자동 로그아웃 경고",
  idle_title: "자동 로그아웃 안내",
  idle_body: "일정 시간 활동이 없어 곧 자동으로 로그아웃됩니다.",
  idle_seconds: "<b>{{n}}</b>초 후 로그아웃됩니다.",
  idle_stay: "계속 이용하기",

  // 로그아웃 확인
  logout_confirm:
    "로그아웃을 하면 개인정보, 일주정보와 채팅 히스토리는 이 기기에서 삭제됩니다.\n\n※ 동일 계정으로 재로그인하면 서버에 보관된 정보는 그대로 복원됩니다.\n\n진행할까요?",

  // 탈퇴 — 확인 게이트(로케일별 확인단어). vi 자판에서도 입력 가능하도록 word 는 로케일별.
  withdraw_confirm:
    "⚠️ 정말 탈퇴하시겠습니까?\n\n탈퇴 시 계정, 개인정보, 사주/일주 정보, 모든 채팅 기록, 보유 포인트 및 결제 이력이 영구적으로 삭제되며 복원할 수 없습니다.",
  withdraw_phrase: "탈퇴",
  withdraw_prompt: "확인을 위해 「{{word}}」 단어를 입력해 주세요.",
  withdraw_cancelled: "탈퇴가 취소되었습니다.",
  withdraw_done: "탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다.",
  withdraw_fail: "탈퇴 실패: {{msg}}",
};

export const shellVi: typeof shellKo = {
  menu: "Menu",
  brand_home: "Về trang chủ",
  sidebar_recent: "Tư vấn gần đây",
  sidebar_empty: "Chưa có buổi tư vấn nào",
  session_delete: "Xóa",
  session_delete_confirm: "Xóa buổi tư vấn này?",
  theme_toggle: "Đổi giao diện",

  tarot_shortcut_title: "Đọc bài Tarot — câu chuyện lá bài kể",
  tarot_shortcut_aria: "Xem đọc bài Tarot",

  biz_ceo: "Người đại diện",
  biz_reg_no: "Mã số doanh nghiệp",
  biz_mailorder: "Đăng ký TMĐT",
  biz_mailorder_pending: "Đang chuẩn bị",
  biz_tel: "Hỗ trợ khách hàng",
  biz_hours: "Giờ làm việc",
  biz_email: "Email",
  biz_privacy_officer: "Người phụ trách bảo vệ dữ liệu cá nhân",
  biz_hosting: "Lưu trữ (hosting)",
  footer_note:
    "Nội dung phản hồi của dịch vụ chỉ mang tính tham khảo, dựa trên tài liệu học tập. Đây không phải tư vấn y tế·pháp lý·đầu tư.",

  idle_aria: "Cảnh báo tự động đăng xuất do không hoạt động",
  idle_title: "Thông báo tự động đăng xuất",
  idle_body: "Do một thời gian không hoạt động, bạn sẽ sớm bị tự động đăng xuất.",
  idle_seconds: "Sẽ tự động đăng xuất sau <b>{{n}}</b> giây.",
  idle_stay: "Tiếp tục sử dụng",

  logout_confirm:
    "Khi đăng xuất, thông tin cá nhân, thông tin lá số và lịch sử trò chuyện sẽ bị xóa khỏi thiết bị này.\n\n※ Nếu đăng nhập lại bằng cùng tài khoản, thông tin lưu trên máy chủ sẽ được khôi phục nguyên vẹn.\n\nBạn có muốn tiếp tục?",

  withdraw_confirm:
    "⚠️ Bạn có chắc chắn muốn hủy tài khoản?\n\nKhi hủy, tài khoản, thông tin cá nhân, dữ liệu Tứ Trụ/lá số, toàn bộ lịch sử trò chuyện, điểm hiện có và lịch sử thanh toán sẽ bị xóa vĩnh viễn và không thể khôi phục.",
  withdraw_phrase: "XÓA",
  withdraw_prompt: "Để xác nhận, vui lòng nhập từ 「{{word}}」.",
  withdraw_cancelled: "Đã hủy thao tác hủy tài khoản.",
  withdraw_done: "Đã hủy tài khoản. Cảm ơn bạn đã sử dụng dịch vụ.",
  withdraw_fail: "Hủy tài khoản thất bại: {{msg}}",
};
