import { Link } from "react-router-dom";

/**
 * 개인정보 사용 화면 공통 고지 — 개인정보보호법 준수 + 약관 기간 후 자동·완전 파기(현행 정책) 안내.
 * 대상: 사주챗/답변·오늘의운세·궁합·작명/개명/아호·택일·신년·1:1 상담 등 개인정보(생년월일·질문·대화) 사용 화면.
 * 실제 파기는 백엔드 배치가 수행(상담 대화 7일, 세션 보관기간 경과분 파기, 회원 탈퇴 시 즉시).
 */
export default function PrivacyNotice({ variant = "answer", what: whatOverride }: { variant?: "answer" | "tool" | "consultation" | "nostore"; what?: string }) {
  const style = {
    margin: "16px 0 8px", padding: "10px 12px", borderRadius: 10,
    fontSize: 12.5, lineHeight: 1.55,
    color: "var(--text-muted, #6b6b6b)",
    background: "var(--surface-2, #f6f4ef)",
    border: "1px solid var(--border, #e7e3da)",
  } as const;
  const legal = (
    // ⚠️ 라우트는 /legal/privacy — /legal 단독 라우트는 없음(클릭 시 빈 화면 사고, 운영자 지적)
    <Link to="/legal/privacy" style={{ color: "inherit", textDecoration: "underline" }}>개인정보처리방침</Link>
  );
  if (variant === "nostore") {
    // 무저장 화면(스낵 테스트 등) — 결과를 저장하지 않음(파기 대상 없음).
    return (
      <div className="privacy-notice" role="note" style={style}>
        🔒 입력하신 생년월일 등은 <b>개인정보보호법</b>에 따라 안전하게 처리되며, <b>이 결과는 별도로 저장하지 않습니다.</b>{" "}
        저장된 사주 프로필은 약관에 따라 관리·파기됩니다. {legal}에서 자세히 확인하실 수 있어요.
      </div>
    );
  }
  const what = whatOverride ??
    (variant === "consultation" ? "질문·대화·사주 명식"
    : variant === "tool" ? "생년월일·이름 등 입력정보와 결과"
    : "생년월일·질문·답변");
  const period = variant === "consultation" ? "상담 종료 후 7일" : "약관에서 정한 보관기간";
  return (
    <div className="privacy-notice" role="note" style={style}>
      🔒 입력하신 {what} 등 개인정보는 <b>개인정보보호법</b>에 따라 안전하게 처리·암호화되며,{" "}
      <b>{period}</b>이 지나면 자동으로 완전 파기됩니다. 회원 탈퇴 시에는 즉시 파기됩니다.{" "}
      {legal}에서 자세히 확인하실 수 있어요.
    </div>
  );
}
