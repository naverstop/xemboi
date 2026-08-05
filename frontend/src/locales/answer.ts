/** AnswerActions(답변 하단 액션바) 문자열 카탈로그 — common.answer 로 병합.
 * 피드백(👍/👎)·평가 사유·nudge·복사/공유/PDF/영상 버튼·오류 alert 문구.
 * 포인트 단위는 문장에 자연스럽게 포함(ko "P" / vi "điểm"); 로그인 필요 alert 은
 * 기존 err.login_required 재사용(여기 미포함). 백엔드 산출값/이벤트 payload 는 제외.
 */
export const answerKo = {
  // 평가(👍/👎) 유도 — 마지막 답변에만
  nudge_q: "이 풀이가 도움이 되었나요? ",
  nudge_reward: "🎁 평점(👍/👎) 주시면 포인트 적립",
  // 👍/👎 버튼 title·aria
  fb_up_title: "추천 — 도움이 됐어요",
  fb_up_aria: "추천",
  fb_down_title: "반대 — 아쉬워요",
  fb_down_aria: "반대",
  // 제출 후 감사 토스트(+리워드)
  fb_thanks: "소중한 의견 감사합니다 🙏",
  fb_reward_toast: " · 🎁 {{amount}}P 적립!",
  // 반대 사유 팝업
  fb_dialog_aria: "답변 평가",
  fb_popup_title: "어떤 점이 아쉬웠나요?",
  fb_popup_ph: "자세히 알려주시면 풀이 개선에 큰 도움이 됩니다 (선택)",
  fb_skip: "건너뛰기",
  fb_submit: "의견 보내기",
  // 반대 사유 5종(선택 시 백엔드 comment 로 전송)
  fb_reason_weak: "근거가 부족해요",
  fb_reason_offtopic: "질문과 다른 답변이에요",
  fb_reason_hard: "내용이 어려워요",
  fb_reason_length: "너무 짧거나 길어요",
  fb_reason_awkward: "표현이 어색해요",
  // 복사
  copy_title: "텍스트 복사",
  copy_btn: "⧉ 텍스트 복사",
  copy_done: "✓ 복사됨",
  copy_fail: "복사에 실패했어요. 본문을 길게 눌러 직접 복사해 주세요.",
  // 공유(상담서 PDF 저장 → 첨부 전달)
  share_title: "상담서 PDF를 저장해 카카오톡·메시지 등에 첨부해 전달하세요",
  share_btn: "↗ 공유",
  share_kakao: "카카오톡으로 보내기", share_zalo: "Zalo로 보내기",
  zalo_copied: "링크를 복사했어요. Zalo 대화방에 붙여넣어 전달해 주세요.",
  share_copy_fail: "링크 복사에 실패했어요. 주소를 직접 전달해 주세요.",
  share_busy: "공유 중…",
  share_done: "✓ 저장됨 — 첨부해 전달",
  share_hint: "상담서 PDF가 저장되었어요. 카카오톡·메시지 등에 첨부해 전달하세요.",
  share_fail: "공유용 PDF 준비 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
  // PDF
  pdf_title: "상담서 PDF",
  pdf_btn: "⤓ PDF",
  pdf_busy: "⏳ 생성 중…",
  pdf_open_title: "생성된 상담서 PDF 열기·저장",
  pdf_open: "⤓ PDF 열기",
  pdf_gen_error: "PDF 생성 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
  // 영상으로 보기
  video_title: "내 사주를 1분 영상으로",
  video_btn: "🎬 영상으로 보기",
  video_busy: "⏳ 시작 중…",
  video_confirm: "내 사주 이야기를 1분 영상으로 만들어 드릴까요?\n\n· {{cost}}P가 차감됩니다(생성 실패 시 자동 환불)\n· 완성되면 하단에서 다운로드할 수 있어요\n· 영상은 48시간 동안만 보관됩니다",
  video_need_charge: "영상 생성에는 {{cost}}P가 필요해요. 충전하면 바로 만들어 드려요.",
  video_fail: "영상 생성을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.",
  // 공유 메뉴(데스크톱/인앱 폴백) — 한도 alert 은 snack.share_quota·err.login_to_share 재사용(여기 미포함)
  share_menu_title: "상담서 PDF 공유",
  share_inapp_guide: "<b>📄 상담서 파일 그대로 보내기</b>지금은 <b>{{name}}</b> 안이라 카톡엔 <b>링크 카드(이미지)</b>만 전달돼요. 파일 그대로 보내려면 아래 <b>⤓ PDF 저장</b> 후, 카톡 채팅방 <b>[＋] → 파일</b>에서 방금 저장한 PDF를 첨부해 보내세요.",
  share_email_item: "메일로 보내기",
  share_link_item: "링크 복사",
  pdf_save_item: "PDF 저장",
  pdf_save_done: "저장 완료",
  share_pc_note: "PC에선 카카오/메일에 파일을 직접 첨부할 수 없어 <b>링크</b>로 전달돼요. 파일 그대로 보내려면 휴대폰에서 공유하세요.",
  link_copy_fail: "링크 복사에 실패했어요. 브라우저 주소를 길게 눌러 복사해 주세요.",
  // 카카오 링크 카드(ko 전용 채널 — vi 는 Zalo 로 대체되지만 타입 완결성 위해 vi 값 유지)
  kakao_card_desc: "상담 내용 전문이 담긴 PDF예요. 카드를 눌러 전체 내용을 확인하세요.",
  kakao_fallback_desc: "상담서 PDF를 확인해 보세요.",
  kakao_card_btn: "상담서 열기",
  kakao_fallback_copied: "카카오 공유를 사용할 수 없어 링크를 복사했어요. 붙여넣어 전달해 주세요.",
  kakao_share_fail: "카카오 공유와 링크 복사에 모두 실패했어요. 주소창의 링크를 직접 전달해 주세요.",
  // 메일 발송(서버 PDF 첨부)
  mail_body: "{{title}}\n\n상담서 PDF 보기: {{url}}\n\n— 인생상담 친구",
  email_to_ph: "받는 사람 이메일",
  email_sending: "보내는 중…",
  email_send_btn: "PDF 첨부 발송",
  email_note: "서버가 PDF를 첨부해 보냅니다. 미설정 시 내 메일앱(링크)으로 열려요.",
  email_invalid: "받는 사람 이메일 주소를 정확히 입력해 주세요.",
  email_need_pdf: "공유용 PDF를 먼저 준비해 주세요.",
  email_login: "메일 발송은 로그인 후 이용할 수 있어요.",
  email_fail: "메일 발송에 실패했어요. 잠시 후 다시 시도하거나 링크 복사로 전달해 주세요.",
  // 한 줄 후기(B-3, 👍 직후 유도)
  rv_aria: "한 줄 후기",
  rv_title: "도움이 되셨다니 기뻐요! 한 줄 후기를 남겨 주시겠어요?",
  rv_star_aria: "별점 선택",
  rv_star_n: "{{n}}점",
  rv_ph: "예) 올해 이직 고민이 있었는데 방향을 잡는 데 도움이 됐어요 (5자 이상)",
  rv_skip: "다음에요",
  rv_submit: "후기 남기기 🎁",
  rv_done: "후기가 접수됐어요! 확인 후 게시되며, 게시되면 포인트가 적립됩니다 🎁",
  rv_fail: "후기 접수에 실패했어요. 잠시 후 다시 시도해 주세요.",
  // 남은 무료 공유 배지(ShareQuotaNote)
  quota_unlimited: "공유 무제한",
  quota_out: "무료 공유를 모두 사용했어요",
  quota_left: "남은 무료 공유 <b>{{n}}</b>회 <of>/ {{limit}}회</of>",
  quota_reset: " · {{date}} 초기화",
};

export const answerVi: typeof answerKo = {
  // 평가(👍/👎) 유도 — 마지막 답변에만
  nudge_q: "Luận giải này có hữu ích cho bạn không? ",
  nudge_reward: "🎁 Đánh giá (👍/👎) để nhận điểm thưởng",
  // 👍/👎 버튼 title·aria
  fb_up_title: "Hữu ích — đã giúp được tôi",
  fb_up_aria: "Hữu ích",
  fb_down_title: "Chưa hài lòng — hơi tiếc",
  fb_down_aria: "Chưa hài lòng",
  // 제출 후 감사 토스트(+리워드)
  fb_thanks: "Cảm ơn ý kiến quý báu của bạn 🙏",
  fb_reward_toast: " · 🎁 Cộng {{amount}} điểm!",
  // 반대 사유 팝업
  fb_dialog_aria: "Đánh giá câu trả lời",
  fb_popup_title: "Bạn chưa hài lòng ở điểm nào?",
  fb_popup_ph: "Chia sẻ chi tiết sẽ giúp chúng tôi cải thiện luận giải rất nhiều (tùy chọn)",
  fb_skip: "Bỏ qua",
  fb_submit: "Gửi ý kiến",
  // 반대 사유 5종
  fb_reason_weak: "Thiếu căn cứ",
  fb_reason_offtopic: "Trả lời không đúng câu hỏi",
  fb_reason_hard: "Nội dung khó hiểu",
  fb_reason_length: "Quá ngắn hoặc quá dài",
  fb_reason_awkward: "Cách diễn đạt gượng gạo",
  // 복사
  copy_title: "Sao chép văn bản",
  copy_btn: "⧉ Sao chép văn bản",
  copy_done: "✓ Đã sao chép",
  copy_fail: "Sao chép thất bại. Vui lòng nhấn giữ nội dung để tự sao chép.",
  // 공유
  share_title: "Lưu PDF tư vấn rồi đính kèm gửi qua Zalo·tin nhắn v.v.",
  share_btn: "↗ Chia sẻ",
  share_kakao: "Gửi qua KakaoTalk", share_zalo: "Gửi qua Zalo",
  zalo_copied: "Đã sao chép liên kết. Dán vào cuộc trò chuyện Zalo để gửi nhé.",
  share_copy_fail: "Sao chép liên kết thất bại. Vui lòng gửi trực tiếp địa chỉ.",
  share_busy: "Đang chia sẻ…",
  share_done: "✓ Đã lưu — đính kèm để gửi",
  share_hint: "Đã lưu PDF tư vấn. Hãy đính kèm gửi qua Zalo·tin nhắn v.v.",
  share_fail: "Đã xảy ra lỗi khi chuẩn bị PDF để chia sẻ. Vui lòng thử lại sau.",
  // PDF
  pdf_title: "PDF tư vấn",
  pdf_btn: "⤓ PDF",
  pdf_busy: "⏳ Đang tạo…",
  pdf_open_title: "Mở·lưu PDF tư vấn đã tạo",
  pdf_open: "⤓ Mở PDF",
  pdf_gen_error: "Đã xảy ra lỗi khi tạo PDF. Vui lòng thử lại sau.",
  // 영상으로 보기
  video_title: "Lá số của bạn thành video 1 phút",
  video_btn: "🎬 Xem bằng video",
  video_busy: "⏳ Đang bắt đầu…",
  video_confirm: "Bạn có muốn biến câu chuyện lá số của bạn thành video 1 phút không?\n\n· Sẽ trừ {{cost}} điểm (tự động hoàn nếu tạo thất bại)\n· Khi hoàn tất, bạn có thể tải xuống ở bên dưới\n· Video chỉ được lưu trong 48 giờ",
  video_need_charge: "Tạo video cần {{cost}} điểm. Nạp điểm là làm được ngay.",
  video_fail: "Không thể bắt đầu tạo video. Vui lòng thử lại sau.",
  // 공유 메뉴 — vi 채널은 카카오 대신 Zalo(커밋 5612bee 결정)
  share_menu_title: "Chia sẻ PDF tư vấn",
  share_inapp_guide: "<b>📄 Gửi nguyên tệp PDF tư vấn</b>Hiện bạn đang ở trong <b>{{name}}</b> nên chỉ gửi được <b>thẻ liên kết (hình ảnh)</b> qua Zalo. Muốn gửi nguyên tệp, hãy bấm <b>⤓ Lưu PDF</b> bên dưới, rồi trong phòng chat Zalo chọn <b>[＋] → Tệp</b> và đính kèm PDF vừa lưu.",
  share_email_item: "Gửi qua email",
  share_link_item: "Sao chép liên kết",
  pdf_save_item: "Lưu PDF",
  pdf_save_done: "Đã lưu",
  share_pc_note: "Trên PC không thể đính kèm tệp trực tiếp vào Zalo/email nên sẽ gửi bằng <b>liên kết</b>. Muốn gửi nguyên tệp, hãy chia sẻ từ điện thoại.",
  link_copy_fail: "Sao chép liên kết thất bại. Hãy nhấn giữ địa chỉ trên trình duyệt để sao chép.",
  // 카카오 링크 카드(ko 전용 채널)
  kakao_card_desc: "PDF chứa toàn văn nội dung tư vấn. Nhấn vào thẻ để xem toàn bộ.",
  kakao_fallback_desc: "Hãy xem PDF tư vấn nhé.",
  kakao_card_btn: "Mở bản tư vấn",
  kakao_fallback_copied: "Không dùng được chia sẻ KakaoTalk nên đã sao chép liên kết. Dán để gửi nhé.",
  kakao_share_fail: "Chia sẻ KakaoTalk và sao chép liên kết đều thất bại. Vui lòng gửi trực tiếp liên kết trên thanh địa chỉ.",
  // 메일 발송
  mail_body: "{{title}}\n\nXem PDF tư vấn: {{url}}\n\n— Xem Bói",
  email_to_ph: "Email người nhận",
  email_sending: "Đang gửi…",
  email_send_btn: "Gửi kèm PDF",
  email_note: "Máy chủ sẽ gửi email kèm PDF. Nếu chưa cấu hình, ứng dụng email của bạn sẽ mở (kèm liên kết).",
  email_invalid: "Vui lòng nhập chính xác địa chỉ email người nhận.",
  email_need_pdf: "Vui lòng chuẩn bị PDF chia sẻ trước.",
  email_login: "Cần đăng nhập để gửi email.",
  email_fail: "Gửi email thất bại. Vui lòng thử lại sau hoặc sao chép liên kết để gửi.",
  // 한 줄 후기
  rv_aria: "Đánh giá một dòng",
  rv_title: "Rất vui vì đã giúp được bạn! Bạn để lại một dòng đánh giá nhé?",
  rv_star_aria: "Chọn số sao",
  rv_star_n: "{{n}} sao",
  rv_ph: "VD) Năm nay tôi băn khoăn chuyện đổi việc, và đã được giúp định hướng (từ 5 ký tự)",
  rv_skip: "Để lần sau",
  rv_submit: "Để lại đánh giá 🎁",
  rv_done: "Đã nhận đánh giá của bạn! Sau khi duyệt sẽ được đăng, và khi đăng bạn sẽ được cộng điểm 🎁",
  rv_fail: "Gửi đánh giá thất bại. Vui lòng thử lại sau.",
  // 남은 무료 공유 배지
  quota_unlimited: "Chia sẻ không giới hạn",
  quota_out: "Đã dùng hết lượt chia sẻ miễn phí",
  quota_left: "Còn <b>{{n}}</b> lượt chia sẻ miễn phí <of>/ {{limit}} lượt</of>",
  quota_reset: " · Đặt lại ngày {{date}}",
};
