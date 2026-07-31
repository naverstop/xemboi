import { useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { api, setCachedMe } from "../api";

/**
 * 면책고지 사전 동의 게이트(최초 1회).
 * 로그인 사용자가 아직 동의하지 않았다면 차단 모달을 띄우고,
 * "동의하고 시작하기"를 눌러야 진행. 동의 시각·버전은 서버에 기록(법적효력).
 */
export default function DisclaimerGate() {
  const { t: tr } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function agree() {
    setBusy(true);
    setErr(null);
    try {
      const me = await api.agreeDisclaimer();
      setCachedMe(me);
    } catch (e: any) {
      setErr(e?.message || tr("misc.gate_fail"));
      setBusy(false);
    }
  }

  return (
    <div className="pwa-overlay" role="alertdialog" aria-modal="true" aria-label={tr("misc.disc_aria")}>
      <div className="pwa-modal disclaimer-modal">
        <h3>{tr("misc.disc_title")}</h3>
        <p className="disclaimer-body">{tr("misc.disc_body")}</p>
        <p className="disclaimer-sub">
          <Trans i18nKey="misc.disc_sub" components={{ b: <strong /> }} />
        </p>
        {err && <p className="disclaimer-err">{err}</p>}
        <div className="pwa-actions">
          <button onClick={agree} disabled={busy}>
            {busy ? tr("misc.processing") : tr("misc.agree_start")}
          </button>
        </div>
        <p className="disclaimer-foot">
          <Trans
            i18nKey="misc.disc_foot"
            components={{ a: <a href="/legal/disclaimer" target="_blank" rel="noreferrer" /> }}
          />
        </p>
      </div>
    </div>
  );
}
