import { useCallback, useEffect, useRef, useState } from "react";

const LAST_ACTIVITY_KEY = "saju_last_activity";
const ACTIVITY_EVENTS: (keyof WindowEventMap)[] = [
  "mousemove",
  "mousedown",
  "keydown",
  "scroll",
  "touchstart",
  "click",
];

type Options = {
  enabled: boolean;
  idleSec?: number;
  warnSec?: number;
  onTimeout: () => void;
};

/**
 * 유휴 자동 로그아웃 훅(계획 7-O).
 * - idleSec 동안 활동이 없으면 onTimeout 호출
 * - 만료 warnSec 전부터 경고(warning=true) 노출, remaining(초) 제공
 * - localStorage 로 멀티탭 활동 동기화
 * - 경고 표시 중에는 일반 활동으로 자동 연장하지 않고 stayActive()로만 연장
 */
export function useIdleTimeout({
  enabled,
  idleSec = 600,
  warnSec = 60,
  onTimeout,
}: Options): { warning: boolean; remaining: number; stayActive: () => void } {
  const [warning, setWarning] = useState(false);
  const [remaining, setRemaining] = useState(idleSec);
  const warningRef = useRef(false);
  const onTimeoutRef = useRef(onTimeout);
  onTimeoutRef.current = onTimeout;

  const touch = useCallback(() => {
    try {
      localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
    } catch {
      /* ignore */
    }
  }, []);

  const stayActive = useCallback(() => {
    touch();
    warningRef.current = false;
    setWarning(false);
    setRemaining(idleSec);
  }, [touch, idleSec]);

  useEffect(() => {
    if (!enabled) {
      setWarning(false);
      warningRef.current = false;
      return;
    }
    touch();

    const onActivity = () => {
      // 경고 노출 중에는 일반 활동으로 연장하지 않는다.
      if (warningRef.current) return;
      touch();
    };
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));

    const onVisible = () => {
      if (document.visibilityState === "visible" && !warningRef.current) touch();
    };
    document.addEventListener("visibilitychange", onVisible);

    const timer = window.setInterval(() => {
      let last = Number(localStorage.getItem(LAST_ACTIVITY_KEY) || 0);
      if (!last) {
        last = Date.now();
        touch();
      }
      const idleMs = Date.now() - last;
      const idleSecNow = Math.floor(idleMs / 1000);
      if (idleSecNow >= idleSec) {
        warningRef.current = false;
        setWarning(false);
        onTimeoutRef.current();
        return;
      }
      if (idleSecNow >= idleSec - warnSec) {
        warningRef.current = true;
        setWarning(true);
        setRemaining(idleSec - idleSecNow);
      } else if (warningRef.current) {
        warningRef.current = false;
        setWarning(false);
      }
    }, 1000);

    return () => {
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, onActivity));
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(timer);
    };
  }, [enabled, idleSec, warnSec, touch]);

  return { warning, remaining, stayActive };
}
