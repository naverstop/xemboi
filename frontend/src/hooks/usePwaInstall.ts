/** PWA 설치 안내 + 푸시 구독 (계획 2.7.6).
 * 플로우: beforeinstallprompt 보관 → 커스텀 팝업 → 승인 시 prompt() 설치
 *         → appinstalled → 푸시 권한 요청 → PushManager.subscribe → 서버 저장.
 * iOS(Safari)는 beforeinstallprompt 미지원 → "공유 → 홈 화면 추가" 가이드.
 */
import { useCallback, useEffect, useState } from "react";
import { api, getToken } from "../api";
import { track } from "../lib/usage";
import { isIOS, isStandalonePwa } from "../lib/inapp";   // iPad(iPadOS13+ = Macintosh UA) 포함 감지 공용

type BIPEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const SNOOZE_KEY = "saju_pwa_snooze_until";
const SNOOZE_DAYS = 7;
const VAPID_PUBLIC = import.meta.env.VITE_VAPID_PUBLIC_KEY as string | undefined;

function snoozed(): boolean {
  const until = Number(localStorage.getItem(SNOOZE_KEY) || 0);
  return Date.now() < until;
}

// 이 기기에서 '설치됨'으로 마킹됐는가 — appinstalled(Android/데스크톱) 또는 사용자의 '이미 설치함' 선택 시 기록.
//  iOS Safari 는 appinstalled 이벤트가 없어 자동 신호가 없으므로, 이 마커가 유일한 '그만 조르기' 근거다.
function installMarked(): boolean {
  return localStorage.getItem("saju_pwa_installed") === "1";
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

/** 현재 브라우저의 푸시 지원/권한/구독 상태. 상담사 알림 토글·배너 판단용. */
export async function getPushState(): Promise<{
  supported: boolean;
  permission: NotificationPermission;
  subscribed: boolean;
}> {
  const supported =
    "serviceWorker" in navigator && "PushManager" in window && !!VAPID_PUBLIC && typeof Notification !== "undefined";
  const permission: NotificationPermission = supported ? Notification.permission : "denied";
  let subscribed = false;
  if (supported) {
    try {
      const reg = await navigator.serviceWorker.ready;
      subscribed = !!(await reg.pushManager.getSubscription());
    } catch {
      /* ignore */
    }
  }
  return { supported, permission, subscribed };
}

/** 푸시 구독 해제 — 브라우저 구독 취소 + 서버 등록 삭제. */
export async function unsubscribePush(): Promise<boolean> {
  if (!("serviceWorker" in navigator)) return false;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      const ep = sub.endpoint;
      await sub.unsubscribe();
      try {
        await api.pushUnsubscribe(ep);
      } catch {
        /* 서버 삭제 실패는 무시(만료 정리는 발송측이 담당) */
      }
    }
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
    // standalone(홈아이콘 실행) 관측 = 이 기기 '설치 확정' → 마커 래칫. iOS 는 appinstalled 이벤트가 없어
    //  이 'standalone 1회 실행'이 유일한 자동 설치신호다(백엔드 usage is_pwa 래칫과 동일 개념). 래칫해 두면
    //  이후 Safari '탭'(비-standalone)으로 들어와도 재프롬프트가 안 뜬다.
    //  [운영자 실측 + 적대검증] 종전엔 standalone 이면 '래칫 없이' 그냥 반환해, 정상 설치자가 탭으로 들어오면
    //  마커가 없어 4초 뒤 iOS 가이드가 또 떴다(수동 '이미 설치함'을 누른 사람만 침묵됐음).
    if (isStandalonePwa()) {
      localStorage.setItem("saju_pwa_installed", "1");
      return;
    }
    if (installMarked()) return;

    const onBIP = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BIPEvent);
      if (!snoozed()) setShowPopup(true);
    };
    window.addEventListener("beforeinstallprompt", onBIP);

    const onInstalled = () => {
      setShowPopup(false);
      setDeferred(null);
      // 설치 확정 카운트(관리자 '현재 통계') + 브라우저 탭에서도 '설치됨'을 알 수 있게 마킹(플로팅 숨김)
      track("click", "pwa:installed");
      localStorage.setItem("saju_pwa_installed", "1");
      window.dispatchEvent(new CustomEvent("saju:pwa-installed"));
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
    track("click", "pwa:install-accept");   // 설치 팝업 '설치' 클릭 카운트
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

  // '이미 설치했어요 · 그만 보기' — iOS 는 appinstalled 자동신호가 없어 이 수동 마킹이 재프롬프트를 멈추는 유일한 길.
  //  마커 기록 + FAB 숨김 이벤트 + 소프트 신호 집계(확정 설치 pwa:installed 와 구분되는 별도 키).
  const markInstalled = useCallback(() => {
    localStorage.setItem("saju_pwa_installed", "1");
    track("click", "pwa:mark-installed");
    window.dispatchEvent(new CustomEvent("saju:pwa-installed"));
    setShowPopup(false);
    setShowIosGuide(false);
  }, []);

  // canInstall = 브라우저가 넘겨준 설치 이벤트를 붙잡아 둔 상태(주로 Android/데스크톱 Chrome).
  //   가이드에서 '한 번에 설치하기' 버튼을 이 값으로 노출한다(스누즈해도 버튼은 유지).
  return { showPopup, showIosGuide, accept, snooze, markInstalled, canInstall: !!deferred };
}
