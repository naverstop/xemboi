/** 생일/시각 입력(BirthFields·TimeSelect) 고유 문자열 카탈로그 — common.birth 로 병합.
 * BirthFields의 대부분 문자열은 chat.* 키를 재사용하고, 여기엔 TimeSelect의
 * 오전/오후·시·분 표기와 BirthFields 고유 문자열(윤달)만 담는다.
 * 시각 값 자체는 백엔드 계약 그대로 24h "HH:MM" — UI 표기만 로케일별.
 */
export const birthKo = {
  // TimeSelect — 오전/오후 토글
  am: "오전",
  pm: "오후",
  ampm_aria: "오전/오후 선택",
  // TimeSelect — 시·분 선택
  hour: "시",
  hour_n: "{{h}}시",
  minute: "분",
  minute_n: "{{mm}}분",
  // BirthFields 고유
  leap: "윤달",
  // readableBirth — '기억된 내 정보' 한 줄 표기('시 모름'·'양력'·'음력'은 chat.* 재사용)
  date_ymd: "{{y}}년 {{m}}월 {{d}}일",
  gender_male: "남자",
  gender_female: "여자",
  lunar_leap: "음력(윤달)",
  // '기억된 내 정보' 강조 카드
  remembered_badge: "🔖 기억된 내 정보",
  remembered_sub: "자동으로 불러왔어요 · 바꾸려면 아래에서 수정하세요",
};

export const birthVi: typeof birthKo = {
  am: "Sáng",
  pm: "Chiều",
  ampm_aria: "Chọn Sáng/Chiều",
  hour: "Giờ",
  hour_n: "{{h}} giờ",
  minute: "Phút",
  minute_n: "{{mm}} phút",
  leap: "Tháng nhuận",
  date_ymd: "{{d}}/{{m}}/{{y}}",
  gender_male: "Nam",
  gender_female: "Nữ",
  lunar_leap: "Âm lịch (tháng nhuận)",
  remembered_badge: "🔖 Thông tin đã lưu của tôi",
  remembered_sub: "Đã tự động điền · muốn thay đổi, hãy sửa bên dưới",
};
