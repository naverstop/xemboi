/** PWA 설치 안내 모달 (계획 2.7.6).
 * - Android/데스크탑: beforeinstallprompt 기반 "설치" 버튼.
 * - iOS Safari: "공유 → 홈 화면에 추가" 가이드.
 */
import { usePwaInstall } from "../hooks/usePwaInstall";

export default function InstallPrompt() {
  const { showPopup, showIosGuide, accept, snooze } = usePwaInstall();

  if (!showPopup && !showIosGuide) return null;

  return (
    <div className="pwa-overlay" onClick={snooze}>
      <div className="pwa-modal" onClick={(e) => e.stopPropagation()}>
        <h3>앱으로 설치하기</h3>
        {showPopup ? (
          <>
            <p>홈 화면에 추가하면 더 빠르게 실행되고, 오늘의 운세 알림을 받을 수 있어요.</p>
            <div className="pwa-actions">
              <button className="secondary" onClick={snooze}>나중에</button>
              <button onClick={accept}>설치</button>
            </div>
          </>
        ) : (
          <>
            <p>
              Safari 하단의 <strong>공유</strong> 버튼을 누른 뒤,
              <strong> &ldquo;홈 화면에 추가&rdquo;</strong>를 선택하면 앱처럼 사용할 수 있어요.
            </p>
            <div className="pwa-actions">
              <button onClick={snooze}>확인</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
