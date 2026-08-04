import { useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { Link } from "react-router-dom";
import { api, setCachedMe } from "../api";

/**
 * 약관 3종(이용약관·개인정보·환불) 사전 동의 게이트.
 * 회원가입 폼을 거치지 않은 SNS 신규 가입자(카카오·구글)는 약관 동의 기록이 없으므로,
 * 로그인 직후 이 차단 게이트로 필수 동의를 받는다. 동의 시각·버전을 서버에 기록(법적효력).
 */
export default function TermsGate() {
  const { t: tr } = useTranslation();
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
      setErr(tr("misc.terms_err_required"));
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
      setErr(e?.message || tr("misc.gate_fail"));
      setBusy(false);
    }
  }

  return (
    <div className="pwa-overlay" role="alertdialog" aria-modal="true" aria-label={tr("misc.terms_aria")}>
      <div className="pwa-modal disclaimer-modal">
        <h3>{tr("misc.terms_title")}</h3>
        <p className="disclaimer-sub">{tr("misc.terms_sub")}</p>
        <div className="auth-agree">
          <label className="agree-all">
            <input type="checkbox" checked={allChecked} onChange={(e) => setAll(e.target.checked)} />
            <span><b>{tr("auth.agree_all")}</b> <em>{tr("auth.agree_all_sub")}</em></span>
          </label>
          <div className="agree-list">
            <label>
              <input type="checkbox" checked={agreeTerms} onChange={(e) => setAgreeTerms(e.target.checked)} />
              <span><i className="req">{tr("auth.req")}</i> <Trans i18nKey="auth.agree_terms" components={{ a: <Link to="/legal/terms" target="_blank" /> }} /></span>
            </label>
            <label>
              <input type="checkbox" checked={agreePrivacy} onChange={(e) => setAgreePrivacy(e.target.checked)} />
              <span><i className="req">{tr("auth.req")}</i> <Trans i18nKey="auth.agree_privacy" components={{ a: <Link to="/legal/privacy" target="_blank" /> }} /></span>
            </label>
            <label>
              <input type="checkbox" checked={agreeRefund} onChange={(e) => setAgreeRefund(e.target.checked)} />
              <span><i className="req">{tr("auth.req")}</i> <Trans i18nKey="misc.agree_refund" components={{ a: <Link to="/legal/refund" target="_blank" /> }} /></span>
            </label>
            <label>
              <input type="checkbox" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
              <span><i className="opt">{tr("auth.opt")}</i> {tr("misc.agree_marketing")}</span>
            </label>
          </div>
        </div>
        {err && <p className="disclaimer-err">{err}</p>}
        <div className="pwa-actions">
          <button onClick={agree} disabled={busy || !allRequired}>
            {busy ? tr("misc.processing") : tr("misc.agree_start")}
          </button>
        </div>
      </div>
    </div>
  );
}
