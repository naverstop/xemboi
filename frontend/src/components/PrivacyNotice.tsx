import { Link } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";

/**
 * 개인정보 사용 화면 공통 고지 — 개인정보보호법 준수 + 약관 기간 후 자동·완전 파기(현행 정책) 안내.
 * 대상: 사주챗/답변·오늘의운세·궁합·작명/개명/아호·택일·신년·1:1 상담 등 개인정보(생년월일·질문·대화) 사용 화면.
 * 실제 파기는 백엔드 배치가 수행(상담 대화 7일, 세션 보관기간 경과분 파기, 회원 탈퇴 시 즉시).
 * 문구는 locales/privacy.ts(common.privacy) — 링크 텍스트도 카탈로그의 <legal> 안에 있다.
 */
export default function PrivacyNotice({ variant = "answer", what: whatOverride }: { variant?: "answer" | "tool" | "consultation" | "nostore"; what?: string }) {
  const { t: tr } = useTranslation();
  const style = {
    margin: "16px 0 8px", padding: "10px 12px", borderRadius: 10,
    fontSize: 12.5, lineHeight: 1.55,
    color: "var(--text-muted, #6b6b6b)",
    background: "var(--surface-2, #f6f4ef)",
    border: "1px solid var(--border, #e7e3da)",
  } as const;
  // ⚠️ 라우트는 /legal/privacy — /legal 단독 라우트는 없음(클릭 시 빈 화면 사고, 운영자 지적)
  const legal = <Link to="/legal/privacy" style={{ color: "inherit", textDecoration: "underline" }} />;
  if (variant === "nostore") {
    // 무저장 화면(스낵 테스트 등) — 결과를 저장하지 않음(파기 대상 없음).
    return (
      <div className="privacy-notice" role="note" style={style}>
        <Trans i18nKey="privacy.nostore" components={{ b: <b />, legal }} />
      </div>
    );
  }
  const what = whatOverride ??
    tr(variant === "consultation" ? "privacy.what_consult"
    : variant === "tool" ? "privacy.what_tool"
    : "privacy.what_answer");
  const period = tr(variant === "consultation" ? "privacy.period_consult" : "privacy.period_default");
  return (
    <div className="privacy-notice" role="note" style={style}>
      <Trans i18nKey="privacy.body" components={{ b: <b />, legal }} values={{ what, period }} />
    </div>
  );
}
