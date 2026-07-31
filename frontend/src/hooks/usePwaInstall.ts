/** PWA 설치 안내 + 푸시 구독 (계획 2.7.6).
 * 플로우: beforeinstallprompt 보관 → 커스텀 팝업 → 승인 시 prompt() 설치
 *         → appinstalled → 푸시 권한 요청 → PushManager.subscribe → 서버 저장.
 * iOS(Safari)는 beforeinstallprompt 미지원 → "공유 → 홈 화면 추가" 가이드.
 */
import { useCallback, useEffect, useState } from "react";
import { api, getToken } from "../api";

type BIPEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const SNOOZE_KEY = "saju_pwa_snooze_until";
const SNOOZE_DAYS = 7;
const VAPID_PUBLIC = import.meta.env.VITE_VAPID_PUBLIC_KEY as string | undefined;

function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    // iOS Safari
    (window.navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

function isIOS(): boolean {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

function snoozed(): boolean {
  const until = Number(localStorage.getItem(SNOOZE_KEY) || 0);
  return Date.now() < until;
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const buf = new ArrayBuffer(raw.length);
  const out = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export async function subscribePush(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;
  if (!VAPID_PUBLIC) return false;
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return false;
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC) as BufferSource,
    });
    const json = sub.toJSON();
    await api.pushSubscribe({
      endpoint: json.endpoint!,
      p256dh: json.keys?.p256dh || "",
      auth: json.keys?.auth || "",
    });
    return true;
  } catch {
    return false;
  }
}

export function usePwaInstall() {
  const [deferred, setDeferred] = useState<BIPEvent | null>(null);
  const [showPopup, setShowPopup] = useState(false);
  const [showIosGuide, setShowIosGuide] = useState(false);

  useEffect(() => {
    if (isStandalone()) return;

    const onBIP = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BIPEvent);
      if (!snoozed()) setShowPopup(true);
    };
    window.addEventListener("beforeinstallprompt", onBIP);

    const onInstalled = () => {
      setShowPopup(false);
      setDeferred(null);
      // 로그인 사용자만 푸시 구독 시도
      if (getToken()) void subscribePush();
    };
    window.addEventListener("appinstalled", onInstalled);

    // iOS는 beforeinstallprompt가 없으므로 가이드로 유도(스누즈 아닐 때)
    if (isIOS() && !snoozed()) {
      const t = setTimeout(() => setShowIosGuide(true), 4000);
      return () => {
        clearTimeout(t);
        window.removeEventListener("beforeinstallprompt", onBIP);
        window.removeEventListener("appinstalled", onInstalled);
      };
    }
    return () => {
      window.removeEventListener("beforeinstallprompt", onBIP);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const accept = useCallback(async () => {
    if (!deferred) return;
    setShowPopup(false);
    await deferred.prompt();
    await deferred.userChoice;
    setDeferred(null);
  }, [deferred]);

  const snooze = useCallback(() => {
    localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_DAYS * 864e5));
    setShowPopup(false);
    setShowIosGuide(false);
  }, []);

  return { showPopup, showIosGuide, accept, snooze };
}
