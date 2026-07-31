import { useState } from "react";
import { api, setCachedMe } from "../api";

/**
 * 면책고지 사전 동의 게이트(최초 1회).
 * 로그인 사용자가 아직 동의하지 않았다면 차단 모달을 띄우고,
 * "동의하고 시작하기"를 눌러야 진행. 동의 시각·버전은 서버에 기록(법적효력).
 */
export default function DisclaimerGate() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function agree() {
    setBusy(true);
    setErr(null);
    try {
      const me = await api.agreeDisclaimer();
      setCachedMe(me);
    } catch (e: any) {
      setErr(e?.message || "동의 처리에 실패했습니다. 다시 시도해 주세요.");
      setBusy(false);
    }
  }

  return (
    <div className="pwa-overlay" role="alertdialog" aria-modal="true" aria-label="면책고지 동의">
      <div className="pwa-modal disclaimer-modal">
        <h3>⚠️ 면책고지 안내</h3>
        <p className="disclaimer-body">
          본 서비스 답변에 의존하여 행한 의사결정의 결과에 대해 회사는 그 어떠한
          법적 책임 및 관련 일체의 책임을 지지 않습니다.
        </p>
        <p className="disclaimer-sub">
          아래 <strong>「동의하고 시작하기」</strong>를 누르는 순간, 사용자는 본 사항에
          대하여 동의한 것으로 간주합니다.
        </p>
        {err && <p className="disclaimer-err">{err}</p>}
        <div className="pwa-actions">
          <button onClick={agree} disabled={busy}>
            {busy ? "처리 중…" : "동의하고 시작하기"}
          </button>
        </div>
        <p className="disclaimer-foot">
          전문(全文)은 <a href="/legal/disclaimer" target="_blank" rel="noreferrer">면책고지</a>에서
          확인할 수 있습니다.
        </p>
      </div>
    </div>
  );
}
