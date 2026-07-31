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
};
