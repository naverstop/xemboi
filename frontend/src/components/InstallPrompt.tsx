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
import { usePwaInstall } from "../hooks/usePwaInstall";
import {
  escapeToExternalBrowser, externalTargetUrl, inAppBrowser,
  isIOS, isIOSSafari, isStandalonePwa as isStandalone,
} from "../lib/inapp";

const AOS_STEPS: { ic: string; text: ReactNode }[] = [
  { ic: "🌐", text: <><b>Chrome</b>으로 이 사이트를 여세요.</> },
  { ic: "⋮", text: <>우측 상단 <b>메뉴(⋮)</b> → <b>&ldquo;앱 설치&rdquo;</b> 또는 <b>&ldquo;홈 화면에 추가&rdquo;</b>를 누르세요.</> },
  { ic: "✅", text: <><b>&ldquo;설치&rdquo;</b>를 누르면 홈 화면과 앱 서랍에 <b>상담친구</b> 앱이 생겨요.</> },
];

export default function InstallPrompt() {
  const { showPopup, showIosGuide, accept, snooze, canInstall } = usePwaInstall();
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
          <h3>📲 앱 설치 안내</h3>
          <div className="pwa-inapp-warn" role="alert">
            <b>⚠️ 지금은 {inApp.name} 안의 브라우저예요.</b><br />
            여기서는 <b>앱 설치(홈 화면 추가)가 안 돼요.</b> {browserName}에서 열면 바로 설치할 수 있어요.
          </div>
          {!copyGuide ? (
            <>
              <button className="pwa-escape" onClick={onEscapeConsent}>
                🧭 {browserName}에서 열기 (동의)
              </button>
              <p className="pwa-note">버튼을 누르면 {browserName}(기기 기본 브라우저)로 이 페이지가 열리고, 설치 안내가 이어집니다.</p>
            </>
          ) : (
            <>
              <div className="pwa-steps" style={{ marginTop: 8 }}>
                <li style={{ listStyle: "none" }}>
                  <span className="pwa-step-ic" aria-hidden>🔗</span>
                  <span className="pwa-step-tx">
                    {copied ? <b>주소가 복사됐어요!</b> : "주소를 복사했어요."} {inApp.name}에서는 자동 이동이 막혀 있어요 —
                    화면 <b>우측 상단/하단 메뉴(⋯)</b>에서 <b>"{browserName}로 열기"</b>를 누르거나,
                    {browserName}를 직접 열어 <b>주소창에 붙여넣기</b> 해주세요.
                  </span>
                </li>
              </div>
              <button className="pwa-escape" onClick={copyLink}>
                {copied ? "✅ 복사됨" : "🔗 주소 다시 복사"}
              </button>
            </>
          )}
          <div className="pwa-actions">
            <button onClick={close}>그냥 둘러보기</button>
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
          <h3>앱으로 설치하기</h3>
          <p>✅ 이미 앱으로 실행 중이에요! 홈 화면 아이콘으로 언제든 바로 열 수 있어요.</p>
          <div className="pwa-actions"><button onClick={close}>확인</button></div>
        </div>
      </div>
    );
  }

  // Android 자동 팝업(설치 버튼 지원)은 기존 흐름 유지 — 한 번에 설치
  if (showPopup && !manualOpen) {
    return (
      <div className="pwa-overlay" onClick={close}>
        <div className="pwa-modal" onClick={(e) => e.stopPropagation()}>
          <h3>앱으로 설치하기</h3>
          <p>홈 화면에 추가하면 더 빠르게 실행되고, 오늘의 운세 알림을 받을 수 있어요.</p>
          <div className="pwa-actions">
            <button className="secondary" onClick={close}>나중에</button>
            <button onClick={installNow}>설치</button>
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
        <h3>📲 앱으로 설치하기</h3>

        {inApp.inApp && (
          <div className="pwa-inapp-warn" role="alert">
            <b>⚠️ 지금은 {inApp.name} 안의 브라우저예요.</b> 여기서는 홈 화면에 추가할 수 없어요.
            {inApp.kakao ? (
              <button className="pwa-escape" onClick={onEscapeConsent}>
                🧭 {isIOS() ? "Safari" : "Chrome"}(기본 브라우저)로 열기
              </button>
            ) : (
              <button className="pwa-escape" onClick={copyLink}>
                {copied ? "✅ 복사됨 — Safari에 붙여넣어 여세요" : "🔗 주소 복사 (Safari에 붙여넣기)"}
              </button>
            )}
          </div>
        )}

        {/* ⭐ 원탭 설치 — 브라우저가 설치 이벤트를 넘겨준 경우(주로 Android/데스크톱 Chrome).
            버튼 한 번이면 네이티브 설치 창이 떠서 바로 설치된다(다른 앱처럼). */}
        {canInstall && !inApp.inApp && (
          <div className="pwa-oneclick">
            <button className="pwa-install-now" onClick={installNow}>📲 한 번에 설치하기</button>
            <p className="pwa-oneclick-note">이 버튼 한 번이면 홈 화면에 <b>상담친구</b> 앱이 설치돼요.</p>
          </div>
        )}

        <div className="pwa-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "ios"} className={tab === "ios" ? "on" : ""} onClick={() => setTab("ios")}> iPhone</button>
          <button role="tab" aria-selected={tab === "aos"} className={tab === "aos" ? "on" : ""} onClick={() => setTab("aos")}>🤖 Android</button>
        </div>

        {tab === "aos" ? (
          <>
            {canInstall ? (
              <p className="pwa-hint pwa-hint-ok">✅ 위 <b>&ldquo;한 번에 설치하기&rdquo;</b> 버튼을 누르면 끝이에요. 버튼이 안 보이면 아래 방법으로도 돼요.</p>
            ) : !inApp.inApp ? (
              <p className="pwa-hint">Chrome에서 잠깐 둘러보시면 <b>&ldquo;한 번에 설치하기&rdquo; 버튼이 자동으로 나타나요.</b> 안 나오면 아래 방법으로 하세요.</p>
            ) : null}
            <ol className="pwa-steps">
              {AOS_STEPS.map((s, i) => (
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
          <button onClick={close}>확인</button>
        </div>
      </div>
    </div>
  );
}

/** iPhone 설치 가이드 — 애플은 원탭 설치 API가 없어, 공유→홈 화면 추가를 '최대한 쉽게' 시각화한다.
 *  - Safari가 아니면(Chrome-iOS·인앱 등): 진짜 설치가 안 되므로 Safari로 유도(주소 복사).
 *  - Safari면: 공유 버튼 위치(하단 가운데) → 공유시트의 '홈 화면에 추가'를 그림+화살표로 안내. */
function IosInstallGuide({ iosSafari, copied, onCopy }: { iosSafari: boolean; copied: boolean; onCopy: () => void }) {
  const [help, setHelp] = useState(false);
  return (
    <div className="pwa-ios">
      {!iosSafari && (
        <div className="pwa-ios-safari" role="alert">
          <b>⚠️ 아이폰은 <u>Safari</u>에서만 앱으로 설치돼요.</b>
          <span>지금 브라우저(크롬 등)에서는 홈 화면에 추가해도 진짜 앱이 안 돼요. 아래 버튼으로 주소를 복사해 <b>Safari</b> 주소창에 붙여넣어 여세요.</span>
          <button className="pwa-escape" onClick={onCopy}>
            {copied ? "✅ 주소 복사됨 — Safari에 붙여넣기" : "🔗 주소 복사 → Safari로 열기"}
          </button>
        </div>
      )}

      {/* 시각 가이드: ① 하단 공유 버튼 위치 ② 공유시트의 '홈 화면에 추가' */}
      <div className="pwa-ios-vis" aria-hidden>
        <div className="pwa-ios-sheet">
          <div className="pwa-ios-row">복사</div>
          <div className="pwa-ios-row hl">
            <span className="pwa-ios-row-tx">홈 화면에 추가</span>
            <span className="pwa-ios-row-ic">➕</span>
          </div>
          <div className="pwa-ios-row">책갈피 추가</div>
          <div className="pwa-ios-arrow">여기를 누르세요</div>
        </div>
        <div className="pwa-ios-bar">
          <span className="pwa-ios-share" title="공유"><i /></span>
          <span className="pwa-ios-bar-tx">① 화면 <b>아래 가운데</b> 공유 버튼</span>
        </div>
      </div>

      <ol className="pwa-steps pwa-ios-steps">
        <li>
          <span className="pwa-step-ic" aria-hidden>⬆️</span><span className="pwa-step-no" aria-hidden>1</span>
          <span className="pwa-step-tx">Safari 화면 <b>아래 가운데 공유 버튼(⬆︎)</b>을 누르세요.</span>
        </li>
        <li>
          <span className="pwa-step-ic" aria-hidden>➕</span><span className="pwa-step-no" aria-hidden>2</span>
          <span className="pwa-step-tx">목록을 아래로 내려 <b>&ldquo;홈 화면에 추가&rdquo;</b>를 누르세요.</span>
        </li>
        <li>
          <span className="pwa-step-ic" aria-hidden>✅</span><span className="pwa-step-no" aria-hidden>3</span>
          <span className="pwa-step-tx">오른쪽 위 <b>&ldquo;추가&rdquo;</b> → 홈 화면의 <b>상담친구</b> 아이콘으로 실행!</span>
        </li>
      </ol>

      <button className="pwa-ios-help-toggle" onClick={() => setHelp((v) => !v)} aria-expanded={help}>
        {help ? "▲ 닫기" : "❓ ‘홈 화면에 추가’가 안 보이나요?"}
      </button>
      {help && (
        <div className="pwa-ios-help">
          <p>• 공유 목록을 <b>아래로 더 스크롤</b>해 보세요. 아래쪽에 있어요.</p>
          <p>• 주소창의 <b>브라우저가 Safari인지</b> 확인하세요. 크롬·카카오·인스타에서는 안 보여요.</p>
          <p>• 그래도 없으면 위 <b>주소 복사</b> 후 Safari를 직접 열어 붙여넣어 주세요.</p>
        </div>
      )}

      <p className="pwa-note">설치하면 전체 화면 앱으로 열리고, iOS 16.4 이상에서는 <b>아침 운세 알림</b>도 받을 수 있어요.</p>
    </div>
  );
}
