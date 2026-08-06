/** PWA 설치 안내 모달 (계획 2.7.6 · 2026-07-11 개편 · 2026-07-29 원탭/아이폰 보완 — 운영자 지시).
 *
 *  - Android/데스크탑: 브라우저가 넘겨준 설치 이벤트(beforeinstallprompt)를 붙잡아 두었다가
 *    가이드 안에서 **"📲 한 번에 설치하기" 버튼 한 번**으로 네이티브 설치를 띄운다.
 *    (자동 팝업을 '나중에'로 스누즈해도 이 버튼은 항상 노출 — 다른 앱처럼 '한 번에 설치'.)
 *  - iPhone/iPad: iOS는 설치 API가 없어 '한 번에'가 원천 불가 → **최대한 쉽게**:
 *    ① 순수 Safari 여부 자동 확인(아니면 Safari로 유도) ② 공유버튼 위치·공유시트를 그림+화살표로
 *    시각화 ③ "안 보여요" 문제해결. (Chrome-iOS·카카오 인앱에선 진짜 설치가 안 되고 Safari에서만 됨)
 *  - 인앱 브라우저(카카오톡·네이버·인스타 등): 홈 화면 추가 불가 → 경고 + 외부 브라우저 탈출(딥링크/복사).
 *  - 상시 진입점: window 이벤트 'saju:open-install-guide'(사이드바·플로팅 "📲 앱 설치")로 스누즈 무관 오픈.
 */
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation, Trans } from "react-i18next";
import { usePwaInstall } from "../hooks/usePwaInstall";
import {
  escapeToExternalBrowser, externalTargetUrl, inAppBrowser,
  isIOS, isIOSSafari, isStandalonePwa as isStandalone,
} from "../lib/inapp";

// Android 설치 단계 — 문구는 install.aos_step* 로케일 키(렌더 시점 해석). 아이콘은 로케일 중립.
function aosSteps(): { ic: string; text: ReactNode }[] {
  return [
    { ic: "🌐", text: <Trans i18nKey="install.aos_step1" components={{ b: <b /> }} /> },
    { ic: "⋮", text: <Trans i18nKey="install.aos_step2" components={{ b: <b /> }} /> },
    { ic: "✅", text: <Trans i18nKey="install.aos_step3" components={{ b: <b /> }} /> },
  ];
}

export default function InstallPrompt() {
  const { t: tr } = useTranslation();
  const { showPopup, showIosGuide, accept, snooze, markInstalled, canInstall } = usePwaInstall();
  const [manualOpen, setManualOpen] = useState(false);            // 상시 진입점(스누즈 무관)
  const [tab, setTab] = useState<"ios" | "aos">(isIOS() ? "ios" : "aos");
  const [copied, setCopied] = useState(false);
  const inApp = inAppBrowser();

  // 인앱 브라우저 자동 경고(운영자 지시: 경고→동의→크롬/사파리 열기→설치 연결).
  const [inAppWarn, setInAppWarn] = useState(false);
  const [copyGuide, setCopyGuide] = useState(false);   // iOS 비카카오 인앱 — 수동 안내 전환
  useEffect(() => {
    if (inApp.inApp && !isStandalone() && sessionStorage.getItem("saju_inapp_warned") !== "1") {
      sessionStorage.setItem("saju_inapp_warned", "1");
      setInAppWarn(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 인앱 탈출로 열린 크롬/사파리: ?install=1 → 설치 가이드 자동 오픈(설치 연결 마무리)
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("install") !== "1") return;
    sp.delete("install");
    const q = sp.toString();
    window.history.replaceState(null, "", window.location.pathname + (q ? "?" + q : ""));
    if (!isStandalone() && !inAppBrowser().inApp) {
      setTab(isIOS() ? "ios" : "aos");
      setManualOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 어디서든 열기 — 사이드바/플로팅 "📲 앱 설치" 버튼 등이 이 이벤트를 쏜다
  useEffect(() => {
    const open = () => { setTab(isIOS() ? "ios" : "aos"); setManualOpen(true); };
    window.addEventListener("saju:open-install-guide", open);
    return () => window.removeEventListener("saju:open-install-guide", open);
  }, []);

  const visible = showPopup || showIosGuide || manualOpen || inAppWarn;
  if (!visible) return null;

  function close() {
    setManualOpen(false);
    setInAppWarn(false);
    setCopyGuide(false);
    snooze();                     // 자동 팝업 경로였다면 7일 스누즈(기존 규약 유지)
  }

  // '이미 설치했어요 · 그만 보기' — iOS 는 설치 자동감지가 없어 재프롬프트를 막는 유일한 수단(영구 마킹).
  function dontShowAgain() {
    markInstalled();
    setManualOpen(false);
    setInAppWarn(false);
    setCopyGuide(false);
  }

  // 원탭 설치 — 붙잡아 둔 이벤트로 네이티브 설치를 띄우고, 성공하면 모달을 닫는다.
  async function installNow() {
    await accept();
    setManualOpen(false);
  }

  // 동의 → 외부 브라우저(크롬/사파리) 열기. iOS 비카카오 인앱은 수동 안내로 전환.
  function onEscapeConsent() {
    const r = escapeToExternalBrowser(true);
    if (r === "copy") {
      copyLink();
      setCopyGuide(true);
    }
  }

  async function copyLink() {
    // 전체 URL(?install=1 포함) 복사 → Safari 붙여넣기 후 설치 가이드가 자동으로 이어짐.
    try {
      await navigator.clipboard.writeText(externalTargetUrl(true));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch { /* 인앱에서 클립보드 실패 시 무시 */ }
  }

  // 인앱 자동 경고 — 경고→동의(크롬/사파리 열기)→탈출한 브라우저에서 설치 가이드 자동 연결
  if (inAppWarn) {
    const browserName = isIOS() ? "Safari" : "Chrome";
    return (
      <div className="pwa-overlay" onClick={close}>
        <div className="pwa-modal pwa-guide" onClick={(e) => e.stopPropagation()}>
          <h3>{tr("install.warn_title")}</h3>
          <div className="pwa-inapp-warn" role="alert">
            <Trans i18nKey="install.warn_body" values={{ name: inApp.name, browser: browserName }} components={{ b: <b />, br: <br /> }} />
          </div>
          {!copyGuide ? (
            <>
              <button className="pwa-escape" onClick={onEscapeConsent}>
                {tr("install.warn_open", { browser: browserName })}
              </button>
              <p className="pwa-note">{tr("install.warn_note", { browser: browserName })}</p>
            </>
          ) : (
            <>
              <div className="pwa-steps" style={{ marginTop: 8 }}>
                <li style={{ listStyle: "none" }}>
                  <span className="pwa-step-ic" aria-hidden>🔗</span>
                  <span className="pwa-step-tx">
                    {copied ? <b>{tr("install.copied_strong")}</b> : tr("install.copied_plain")}{" "}
                    <Trans i18nKey="install.copy_guide" values={{ name: inApp.name, browser: browserName }} components={{ b: <b /> }} />
                  </span>
                </li>
              </div>
              <button className="pwa-escape" onClick={copyLink}>
                {copied ? tr("install.copy_again_done") : tr("install.copy_again")}
              </button>
            </>
          )}
          <div className="pwa-actions">
            <button onClick={close}>{tr("install.just_browse")}</button>
          </div>
        </div>
      </div>
    );
  }

  // 이미 설치된(standalone) 상태에서 수동으로 열었으면 완료 안내만
  if (manualOpen && isStandalone()) {
    return (
      <div className="pwa-overlay" onClick={close}>
        <div className="pwa-modal" onClick={(e) => e.stopPropagation()}>
          <h3>{tr("misc.pwa_title")}</h3>
          <p>{tr("install.already_installed")}</p>
          <div className="pwa-actions"><button onClick={close}>{tr("misc.pwa_confirm")}</button></div>
        </div>
      </div>
    );
  }

  // Android 자동 팝업(설치 버튼 지원)은 기존 흐름 유지 — 한 번에 설치
  if (showPopup && !manualOpen) {
    return (
      <div className="pwa-overlay" onClick={close}>
        <div className="pwa-modal" onClick={(e) => e.stopPropagation()}>
          <h3>{tr("misc.pwa_title")}</h3>
          <p>{tr("misc.pwa_popup_body")}</p>
          <div className="pwa-actions">
            <button className="secondary" onClick={close}>{tr("misc.pwa_later")}</button>
            <button onClick={installNow}>{tr("misc.pwa_install")}</button>
          </div>
        </div>
      </div>
    );
  }

  // ── 단계별 가이드(iOS 자동 안내 + 수동 오픈 공용) ─────────────────────────────
  const iosSafari = isIOSSafari();
  return (
    <div className="pwa-overlay" onClick={close}>
      <div className="pwa-modal pwa-guide" onClick={(e) => e.stopPropagation()}>
        <h3>📲 {tr("misc.pwa_title")}</h3>

        {inApp.inApp && (
          <div className="pwa-inapp-warn" role="alert">
            <Trans i18nKey="install.guide_inapp" values={{ name: inApp.name }} components={{ b: <b /> }} />
            {inApp.kakao ? (
              <button className="pwa-escape" onClick={onEscapeConsent}>
                {tr("install.open_default", { browser: isIOS() ? "Safari" : "Chrome" })}
              </button>
            ) : (
              <button className="pwa-escape" onClick={copyLink}>
                {copied ? tr("install.copy_safari_done") : tr("install.copy_safari")}
              </button>
            )}
          </div>
        )}

        {/* ⭐ 원탭 설치 — 브라우저가 설치 이벤트를 넘겨준 경우(주로 Android/데스크톱 Chrome).
            버튼 한 번이면 네이티브 설치 창이 떠서 바로 설치된다(다른 앱처럼). */}
        {canInstall && !inApp.inApp && (
          <div className="pwa-oneclick">
            <button className="pwa-install-now" onClick={installNow}>{tr("install.oneclick_btn")}</button>
            <p className="pwa-oneclick-note"><Trans i18nKey="install.oneclick_note" components={{ b: <b /> }} /></p>
          </div>
        )}

        <div className="pwa-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "ios"} className={tab === "ios" ? "on" : ""} onClick={() => setTab("ios")}> iPhone</button>
          <button role="tab" aria-selected={tab === "aos"} className={tab === "aos" ? "on" : ""} onClick={() => setTab("aos")}>🤖 Android</button>
        </div>

        {tab === "aos" ? (
          <>
            {canInstall ? (
              <p className="pwa-hint pwa-hint-ok"><Trans i18nKey="install.aos_hint_ok" components={{ b: <b /> }} /></p>
            ) : !inApp.inApp ? (
              <p className="pwa-hint"><Trans i18nKey="install.aos_hint" components={{ b: <b /> }} /></p>
            ) : null}
            <ol className="pwa-steps">
              {aosSteps().map((s, i) => (
                <li key={i}>
                  <span className="pwa-step-ic" aria-hidden>{s.ic}</span>
                  <span className="pwa-step-no" aria-hidden>{i + 1}</span>
                  <span className="pwa-step-tx">{s.text}</span>
                </li>
              ))}
            </ol>
          </>
        ) : (
          <IosInstallGuide iosSafari={iosSafari} copied={copied} onCopy={copyLink} />
        )}

        <div className="pwa-actions">
          <button className="secondary" onClick={dontShowAgain}>{tr("misc.pwa_installed_dismiss")}</button>
          <button onClick={close}>{tr("misc.pwa_confirm")}</button>
        </div>
      </div>
    </div>
  );
}

/** iPhone 설치 가이드 — 애플은 원탭 설치 API가 없어, 공유→홈 화면 추가를 '최대한 쉽게' 시각화한다.
 *  - Safari가 아니면(Chrome-iOS·인앱 등): 진짜 설치가 안 되므로 Safari로 유도(주소 복사).
 *  - Safari면: 공유 버튼 위치(하단 가운데) → 공유시트의 '홈 화면에 추가'를 그림+화살표로 안내. */
function IosInstallGuide({ iosSafari, copied, onCopy }: { iosSafari: boolean; copied: boolean; onCopy: () => void }) {
  const { t: tr } = useTranslation();
  const [help, setHelp] = useState(false);
  return (
    <div className="pwa-ios">
      {!iosSafari && (
        <div className="pwa-ios-safari" role="alert">
          <Trans i18nKey="install.ios_only_safari" components={{ b: <b />, u: <u /> }} />
          <span><Trans i18nKey="install.ios_safari_body" components={{ b: <b /> }} /></span>
          <button className="pwa-escape" onClick={onCopy}>
            {copied ? tr("install.ios_copy_done") : tr("install.ios_copy")}
          </button>
        </div>
      )}

      {/* 시각 가이드: ① 하단 공유 버튼 위치 ② 공유시트의 '홈 화면에 추가' */}
      <div className="pwa-ios-vis" aria-hidden>
        <div className="pwa-ios-sheet">
          <div className="pwa-ios-row">{tr("install.sheet_copy")}</div>
          <div className="pwa-ios-row hl">
            <span className="pwa-ios-row-tx">{tr("install.sheet_add_home")}</span>
            <span className="pwa-ios-row-ic">➕</span>
          </div>
          <div className="pwa-ios-row">{tr("install.sheet_bookmark")}</div>
          <div className="pwa-ios-arrow">{tr("install.sheet_tap_here")}</div>
        </div>
        <div className="pwa-ios-bar">
          <span className="pwa-ios-share" title={tr("install.sheet_share_title")}><i /></span>
          <span className="pwa-ios-bar-tx"><Trans i18nKey="install.sheet_bar_hint" components={{ b: <b /> }} /></span>
        </div>
      </div>

      <ol className="pwa-steps pwa-ios-steps">
        <li>
          <span className="pwa-step-ic" aria-hidden>⬆️</span><span className="pwa-step-no" aria-hidden>1</span>
          <span className="pwa-step-tx"><Trans i18nKey="install.ios_step1" components={{ b: <b /> }} /></span>
        </li>
        <li>
          <span className="pwa-step-ic" aria-hidden>➕</span><span className="pwa-step-no" aria-hidden>2</span>
          <span className="pwa-step-tx"><Trans i18nKey="install.ios_step2" components={{ b: <b /> }} /></span>
        </li>
        <li>
          <span className="pwa-step-ic" aria-hidden>✅</span><span className="pwa-step-no" aria-hidden>3</span>
          <span className="pwa-step-tx"><Trans i18nKey="install.ios_step3" components={{ b: <b /> }} /></span>
        </li>
      </ol>

      <button className="pwa-ios-help-toggle" onClick={() => setHelp((v) => !v)} aria-expanded={help}>
        {help ? tr("install.help_close") : tr("install.help_open")}
      </button>
      {help && (
        <div className="pwa-ios-help">
          <p><Trans i18nKey="install.help1" components={{ b: <b /> }} /></p>
          <p><Trans i18nKey="install.help2" components={{ b: <b /> }} /></p>
          <p><Trans i18nKey="install.help3" components={{ b: <b /> }} /></p>
        </div>
      )}

      <p className="pwa-note"><Trans i18nKey="install.ios_note" components={{ b: <b /> }} /></p>
    </div>
  );
}
