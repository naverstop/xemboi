/** lib 잔여·소형 공용 컴포넌트 문자열 카탈로그 — common.libx 로 병합(ns "libx").
 *  ⚠️ i18n.ts 등록은 메인이 일괄 수행(등록 전에는 키 원문이 노출될 수 있음 — 과도기 정상).
 *  대상: PastResultsDrawer · ProgressDock(잔여) · RememberBirth · lib/sse · lib/displayName.
 */
export const libxKo = {
  // PastResultsDrawer — '지난 결과' 재열람 드로어
  past_label: "지난 결과",
  past_note: "🕰 지난 결과는 언제든 다시 볼 수 있어요 — 재열람은 포인트가 차감되지 않아요.",
  past_empty: "아직 저장된 결과가 없어요.",
  past_title: "입장료 없이 지난 결과를 다시 봅니다",
  loading: "불러오는 중…",

  // ProgressDock — 영상 카드 잔여(만료·로드 실패)
  vid_expired: "보관 기간이 지나 영상이 삭제되었어요.",
  vid_load_fail: "영상 파일을 불러오지 못했어요.",

  // RememberBirth — '내 사주정보 기억하기' 토글
  remember_tip: "켜 두면 입력한 사주정보를 저장해, 어느 메뉴에서든 자동으로 불러옵니다.",
  remember_label: "💾 내 사주정보 기억하기",
  remember_on: "모든 메뉴에서 자동 입력돼요",
  remember_off: "켜면 매번 입력 안 해도 돼요",

  // lib/sse.ts — 스트림 오류 폴백
  stream_error: "스트림 오류",
  // lib/displayName.ts — 호칭 기본 폴백
  dn_customer: "고객",
};

export const libxVi: typeof libxKo = {
  past_label: "Kết quả trước",
  past_note: "🕰 Bạn có thể xem lại kết quả cũ bất cứ lúc nào — xem lại không bị trừ điểm.",
  past_empty: "Chưa có kết quả nào được lưu.",
  past_title: "Xem lại kết quả cũ mà không mất phí vào cửa",
  loading: "Đang tải…",

  vid_expired: "Video đã bị xóa do hết thời hạn lưu trữ.",
  vid_load_fail: "Không tải được tệp video.",

  remember_tip: "Bật để lưu thông tin đã nhập và tự động điền ở mọi mục.",
  remember_label: "💾 Ghi nhớ thông tin của tôi",
  remember_on: "Tự động điền ở mọi mục",
  remember_off: "Bật lên thì không cần nhập lại mỗi lần",

  stream_error: "Lỗi luồng dữ liệu",
  dn_customer: "Quý khách",
};
