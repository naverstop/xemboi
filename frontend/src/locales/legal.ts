/** LegalPage(법적 고지 4종) UI 크롬 문자열 카탈로그 — common.legal 로 병합.
 * 문서 본문(약관·개인정보·환불·면책 조문)은 법적으로 민감하여 여기서 번역하지 않는다
 * (LegalPage.tsx의 Terms/Privacy/Refund/Disclaimer/BizTable 컴포넌트 = 정책 원문 영역).
 * 여기서는 문서 제목(제목/탭·네비 라벨)과 '관련 문서' 라벨 등 화면 크롬만 담는다.
 */
export const legalKo = {
  title_terms: "이용약관",
  title_privacy: "개인정보처리방침",
  title_refund: "환불·청약철회 정책",
  title_disclaimer: "면책고지",
  related: "관련 문서",
};

export const legalVi: typeof legalKo = {
  title_terms: "Điều khoản sử dụng",
  title_privacy: "Chính sách quyền riêng tư",
  title_refund: "Chính sách hoàn tiền·hủy giao dịch",
  title_disclaimer: "Tuyên bố miễn trừ",
  related: "Tài liệu liên quan",
};
