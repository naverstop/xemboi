import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { subscribePush, getPushState } from "../hooks/usePwaInstall";

/**
 * 상담사 알림 자동 구독 — 로그인된 상담사면:
 * - 이미 알림 허용됨 → 무음으로 구독 재등록(서버에 상담사 user_id로 저장, ID 매칭 자동)
 * - 아직 미허용(default) → '알림 켜기' 배너 노출(1클릭 = 브라우저 권한요청+구독; 제스처 규칙 준수)
 * - 차단됨(denied) → 아무 것도 안 함
 * 브라우저 보안상 최초 1회 허용 클릭은 우회 불가. iOS는 홈화면 추가(PWA) 후에만 푸시 가능.
 */
const SNOOZE_KEY = "saju_consult_push_snooze";
const SNOOZE_MS = 3 * 864e5; // 3일

export default function ConsultantPushPrompt({ active }: { active: boolean }) {
  const { t: tr } = useTranslation();
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!active) { setShow(false); return; }
    let alive = true;
    (async () => {
      const st = await getPushState();
      if (!alive || !st.supported) return;
      if (st.permission === "granted") {
        if (!st.subscribed) void subscribePush();  // 재방문 무음 재등록
        return;
      }
      if (st.permission === "denied") return;
      if (Date.now() >= Number(localStorage.getItem(SNOOZE_KEY) || 0)) setShow(true);
    })();
    return () => { alive = false; };
  }, [active]);

  if (!show) return null;

  async function allow() {
    setBusy(true);
    const ok = await subscribePush();
    setBusy(false);
    setShow(false);
    if (!ok) localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_MS));
  }
  function later() {
    localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_MS));
    setShow(false);
  }

  return (
    <div className="cpush-banner" role="alert">
      <span className="cpush-ic" aria-hidden>🔔</span>
      <div className="cpush-tx">
        <b>{tr("consult.push_title")}</b>
        <span>{tr("consult.push_sub")}</span>
      </div>
      <button className="cpush-allow" onClick={allow} disabled={busy}>{busy ? tr("consult.push_setting") : tr("consult.push_allow")}</button>
      <button className="cpush-later" onClick={later} aria-label={tr("consult.push_later")}>✕</button>
    </div>
  );
}
