/** 앱 공유 플로팅(FAB) — 설치 완료 사용자에게 '앱 설치' 버튼이 사라진 자리에 노출(운영자 지시 2026-07-18).
 *  클릭 → OS 공유 시트(카카오톡·메시지 등)로 '설치유도 링크(?install=1)' 전달. 데스크톱은 링크 복사 폴백.
 *  수신자가 링크를 열면 인앱 탈출→크롬/사파리→설치 가이드로 이어진다(lib/appShare · InstallPrompt).
 */
import { useRef, useState } from "react";
import { shareApp } from "../lib/appShare";
import { track } from "../lib/usage";

export default function ShareFab() {
  const [label, setLabel] = useState<string | null>(null);
  const busyRef = useRef(false);

  async function onClick() {
    if (busyRef.current) return;
    busyRef.current = true;
    track("click", "app:share");
    try {
      const r = await shareApp();
      // r === "shared" → OS 공유 시트가 처리(라벨 변경 없음). 복사/실패만 잠깐 안내.
      if (r === "copied" || r === "failed") {
        setLabel(r === "copied" ? "✓ 링크 복사됨" : "복사 실패");
        window.setTimeout(() => setLabel(null), 2200);
      }
    } finally {
      busyRef.current = false;
    }
  }

  return (
    <button className="share-fab" aria-label="앱 공유하기 — 친구에게 링크로 전달" onClick={onClick}>
      <span className="share-fab-ic" aria-hidden>📤</span>
      <span className="share-fab-tx">{label ?? "공유"}</span>
    </button>
  );
}
