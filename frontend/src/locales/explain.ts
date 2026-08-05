/** 공용 해설(ExplainChat) + 추가질문 과금바(FollowupBilling) 문자열 카탈로그 — common.explain 로 병합.
 * 궁합·택일·작명 등에서 공유하는 미리보기/추가질문/과금 안내. compat·chat 유사 키는 그쪽을 재사용하고,
 * 공용(범용) 문구만 여기에 둔다. 포인트 단위는 pay.pt(=điểm) 재사용.
 */
export const explainKo = {
  // 미리보기 잠금 안내 (문장 내 <b> — Trans)
  preview_lock: "🔒 여기까지는 <b>미리보기</b>예요 —",
  preview_member: "전체 해설은 충전 후 이용할 수 있어요.",
  preview_guest: "로그인하면 전체 해설과 추가 질문을 볼 수 있어요.",
  // 추가질문 입력 placeholder (범용 — 궁합/택일/작명 공용)
  qa_ph: "결과에 대해 더 물어보세요",
  // 감정서 주제
  report_topic: "상담",
  report_topic_item: "{{item}} 상담",
  // FollowupBilling 과금바
  fb_depth_aria: "추가질문 등급",
  fb_guest: "로그인 후 추가 질문 (1일 무료 또는 크레딧 차감)",
  fb_free: "이번 질문 무료 👍 · 남은 무료 {{rem}}회",
  fb_paid: "{{level}} 질문 · {{cost}}P 차감 예정 · 잔액 {{bal}}P",
  // FollowupBilling 차감 배지(하단 강조 줄)
  fb_locked: "로그인 후 추가 질문 (크레딧 차감)",
  fb_charge: "{{level}} 질문 <b>{{cost}}P 차감</b>",
  fb_disc: "플러스 {{pct}}% 할인",
  // ExplainChat 해설 블록('보강 중'은 compat.refining, '추가 질문' 폴백은 compat.qa_title 재사용)
  head: "해설",
  cta: "🔮 자세히 설명해 드릴까요?",
  included_tag: "입장료 포함",
  free_tag: "무료",
  delay: "해설 생성이 지연되고 있어요. 네트워크나 서버 사정일 수 있어요.",
  retry_btn: "🔄 다시 시도 (무과금)",
  generating: "🔮 <b>설명을 생성하고 있어요</b>",
  q_prefix: "[질문]",
};

export const explainVi: typeof explainKo = {
  preview_lock: "🔒 Đến đây là <b>bản xem trước</b> —",
  preview_member: "Luận giải đầy đủ có thể xem sau khi nạp điểm.",
  preview_guest: "Đăng nhập để xem luận giải đầy đủ và hỏi thêm.",
  qa_ph: "Hỏi thêm về kết quả",
  report_topic: "Tư vấn",
  report_topic_item: "Tư vấn {{item}}",
  fb_depth_aria: "Mức câu hỏi thêm",
  fb_guest: "Đăng nhập để hỏi thêm (miễn phí 1 lần/ngày hoặc trừ điểm)",
  fb_free: "Câu hỏi này miễn phí 👍 · còn {{rem}} lần miễn phí",
  fb_paid: "Câu hỏi {{level}} · sẽ trừ {{cost}} điểm · số dư {{bal}} điểm",
  fb_locked: "Đăng nhập để hỏi thêm (trừ điểm)",
  fb_charge: "Câu hỏi {{level}} · <b>trừ {{cost}} điểm</b>",
  fb_disc: "Gói Plus giảm {{pct}}%",
  head: "Luận giải",
  cta: "🔮 Muốn tôi giải thích chi tiết hơn không?",
  included_tag: "Đã gồm trong phí vào",
  free_tag: "Miễn phí",
  delay: "Việc tạo luận giải đang bị chậm. Có thể do mạng hoặc máy chủ.",
  retry_btn: "🔄 Thử lại (không tính phí)",
  generating: "🔮 <b>Đang tạo phần giải thích</b>",
  q_prefix: "[Câu hỏi]",
};
