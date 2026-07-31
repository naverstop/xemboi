import { useState } from "react";
import { Link } from "react-router-dom";
import { api, setCachedMe } from "../api";

/**
 * 약관 3종(이용약관·개인정보·환불) 사전 동의 게이트.
 * 회원가입 폼을 거치지 않은 SNS 신규 가입자(카카오·구글)는 약관 동의 기록이 없으므로,
 * 로그인 직후 이 차단 게이트로 필수 동의를 받는다. 동의 시각·버전을 서버에 기록(법적효력).
 */
export default function TermsGate() {
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);
  const [agreeRefund, setAgreeRefund] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const allRequired = agreeTerms && agreePrivacy && agreeRefund;
  const allChecked = allRequired && marketing;
  function setAll(v: boolean) {
    setAgreeTerms(v); setAgreePrivacy(v); setAgreeRefund(v); setMarketing(v);
  }

  async function agree() {
    if (!allRequired) {
      setErr("필수 약관 3개에 모두 동의해야 합니다.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const me = await api.agreeTerms({
        agree_terms: agreeTerms,
        agree_privacy: agreePrivacy,
        agree_refund: agreeRefund,
        marketing_opt_in: marketing,
      });
      setCachedMe(me);
    } catch (e: any) {
      setErr(e?.message || "동의 처리에 실패했습니다. 다시 시도해 주세요.");
      setBusy(false);
    }
  }

  return (
    <div className="pwa-overlay" role="alertdialog" aria-modal="true" aria-label="약관 동의">
      <div className="pwa-modal disclaimer-modal">
        <h3>📋 서비스 이용 약관 동의</h3>
        <p className="disclaimer-sub">
          서비스 이용을 위해 약관 동의가 필요합니다. 필수 항목에 동의해 주세요.
        </p>
        <div className="auth-agree">
          <label className="agree-all">
            <input type="checkbox" checked={allChecked} onChange={(e) => setAll(e.target.checked)} />
            <span><b>전체 동의</b> <em>(필수 및 선택 항목 모두 포함)</em></span>
          </label>
          <div className="agree-list">
            <label>
              <input type="checkbox" checked={agreeTerms} onChange={(e) => setAgreeTerms(e.target.checked)} />
              <span><i className="req">필수</i> <Link to="/legal/terms" target="_blank">이용약관</Link>에 동의합니다.</span>
            </label>
            <label>
              <input type="checkbox" checked={agreePrivacy} onChange={(e) => setAgreePrivacy(e.target.checked)} />
              <span><i className="req">필수</i> <Link to="/legal/privacy" target="_blank">개인정보 수집·이용</Link>에 동의합니다.</span>
            </label>
            <label>
              <input type="checkbox" checked={agreeRefund} onChange={(e) => setAgreeRefund(e.target.checked)} />
              <span><i className="req">필수</i> <Link to="/legal/refund" target="_blank">환불정책</Link>에 동의합니다.</span>
            </label>
            <label>
              <input type="checkbox" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
              <span><i className="opt">선택</i> 마케팅 정보 수신에 동의합니다.</span>
            </label>
          </div>
        </div>
        {err && <p className="disclaimer-err">{err}</p>}
        <div className="pwa-actions">
          <button onClick={agree} disabled={busy || !allRequired}>
            {busy ? "처리 중…" : "동의하고 시작하기"}
          </button>
        </div>
      </div>
    </div>
  );
}
