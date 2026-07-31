/** PWA 설치 안내 모달 (계획 2.7.6).
 * - Android/데스크탑: beforeinstallprompt 기반 "설치" 버튼.
 * - iOS Safari: "공유 → 홈 화면에 추가" 가이드.
 */
import { useTranslation, Trans } from "react-i18next";
import { usePwaInstall } from "../hooks/usePwaInstall";

export default function InstallPrompt() {
  const { t: tr } = useTranslation();
  const { showPopup, showIosGuide, accept, snooze } = usePwaInstall();

  if (!showPopup && !showIosGuide) return null;

  return (
    <div className="pwa-overlay" onClick={snooze}>
      <div className="pwa-modal" onClick={(e) => e.stopPropagation()}>
        <h3>{tr("misc.pwa_title")}</h3>
        {showPopup ? (
          <>
            <p>{tr("misc.pwa_popup_body")}</p>
            <div className="pwa-actions">
              <button className="secondary" onClick={snooze}>{tr("misc.pwa_later")}</button>
              <button onClick={accept}>{tr("misc.pwa_install")}</button>
            </div>
          </>
        ) : (
          <>
            <p>
              <Trans i18nKey="misc.pwa_ios_body" components={{ b: <strong /> }} />
            </p>
            <div className="pwa-actions">
              <button onClick={snooze}>{tr("misc.pwa_confirm")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
