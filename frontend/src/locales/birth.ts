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
};
