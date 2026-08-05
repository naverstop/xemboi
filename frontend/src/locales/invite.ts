/** CompatInvitePage(궁합 초대 랜딩) 문자열 카탈로그 — common.invite 로 병합.
 * ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어.
 * 등급(grade)·티저 문구(line)·축 라벨(axes[].label)은 백엔드 산출값이라 여기 없음.
 */
export const inviteKo = {
  err_notfound: "초대를 찾을 수 없어요.",
  err_calc: "궁합 계산에 실패했어요.",
  hero_badge: "宮合",
  hero_title: "궁합 초대장",
  hero_desc: "<b>{{name}}</b>님이 궁합을 확인하고 싶어 해요. <b>내 생년월일만</b> 입력하면 두 분의 궁합 등급을 바로 볼 수 있어요. 무료!",
  teaser_ready: "두 분의 궁합 결과가 나왔어요 👇",
  expired: "이 초대는 만료됐어요(7일). 상대방에게 새 초대를 부탁해 보세요.",
  privacy_note: "입력한 생년월일은 궁합 계산과 초대자에게 결과를 이어 보여주는 데에만 쓰여요.",
  busy: "궁합 보는 중…",
  cta: "💞 우리 궁합 확인하기 (무료)",
  total_pts: "{{n}}점",
  lock: "🔒 여기까지는 맛보기",
  cta_desc: "<b>자세한 점수와 다섯 영역 풀이, AI 해설</b>은 사이트(궁합 메뉴)에서 제공돼요 — 합·충·오행·십성·신살을 <b>세 관점</b>으로 깊이 있게 풀어드립니다.",
  cta_link: "🔮 사이트에서 전체 궁합 풀이 보기",
};

export const inviteVi: typeof inviteKo = {
  err_notfound: "Không tìm thấy lời mời.",
  err_calc: "Tính toán xem tuổi thất bại.",
  hero_badge: "💌",
  hero_title: "Thiệp mời xem tuổi",
  hero_desc: "<b>{{name}}</b> muốn xem tuổi cùng bạn. Chỉ cần nhập <b>ngày sinh của bạn</b> là thấy ngay cấp độ hợp tuổi của hai người. Miễn phí!",
  teaser_ready: "Kết quả xem tuổi của hai bạn đã có 👇",
  expired: "Lời mời này đã hết hạn (7 ngày). Hãy nhờ đối phương gửi lời mời mới nhé.",
  privacy_note: "Ngày sinh bạn nhập chỉ dùng để tính xem tuổi và hiển thị kết quả cho người mời.",
  busy: "Đang xem tuổi…",
  cta: "💞 Xem tuổi hai chúng ta (miễn phí)",
  total_pts: "{{n}} điểm",
  lock: "🔒 Đến đây là bản xem thử",
  cta_desc: "<b>Điểm chi tiết, luận giải năm lĩnh vực và AI giải thích</b> có tại trang web (mục Xem tuổi) — luận sâu hợp·xung·ngũ hành·thập thần·thần sát theo <b>ba góc nhìn</b>.",
  cta_link: "🔮 Xem trọn bộ luận giải xem tuổi trên trang web",
};
