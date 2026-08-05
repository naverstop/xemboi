/** ReviewsPage(이용 후기)·ReviewStrip 문자열 카탈로그 — common.reviews 로 병합.
 * ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어.
 * 후기 본문·표시명·source_label 은 백엔드 산출값이라 여기 없음.
 */
export const reviewsKo = {
  f_all: "전체",
  f_chat: "사주 상담",
  f_compat: "궁합",
  f_tarot: "타로",
  f_tool: "택일·작명",
  f_sinnyeon: "신년운세",
  f_consult: "1:1 상담",
  hero_badge: "後記",
  hero_title: "이용 후기",
  hero_desc: "실제 이용자들이 남긴 <b>진짜 후기</b>예요. 상담 답변 아래 👍를 누르면 후기를 남길 수 있고, 게시가 확정되면 <b>포인트를 적립</b>해 드려요.",
  filter_aria: "메뉴 필터",
  loading: "후기를 불러오는 중…",
  empty: "아직 게시된 후기가 없어요. 첫 후기의 주인공이 되어 주세요 — 상담 답변 아래 👍를 누르면 남길 수 있어요.",
  stars_aria: "별점 {{n}}점",
};

export const reviewsVi: typeof reviewsKo = {
  f_all: "Tất cả",
  f_chat: "Tư vấn Tứ Trụ",
  f_compat: "Xem tuổi",
  f_tarot: "Tarot",
  f_tool: "Xem ngày·đặt tên",
  f_sinnyeon: "Vận trình năm mới",
  f_consult: "Tư vấn 1:1",
  hero_badge: "⭐",
  hero_title: "Đánh giá của người dùng",
  hero_desc: "Đây là những <b>đánh giá thật</b> từ người dùng thực tế. Nhấn 👍 dưới câu trả lời tư vấn để để lại đánh giá; khi được duyệt đăng, bạn sẽ được <b>cộng điểm</b>.",
  filter_aria: "Bộ lọc theo mục",
  loading: "Đang tải đánh giá…",
  empty: "Chưa có đánh giá nào được đăng. Hãy là người đầu tiên — nhấn 👍 dưới câu trả lời tư vấn để để lại đánh giá nhé.",
  stars_aria: "Xếp hạng {{n}} sao",
};
