/** 사용 현황 수집(관리자 '현재 통계' 탭 데이터 소스) — 운영자 지시 2026-07-11.
 *
 *  - 기기 식별: localStorage 랜덤 uuid(개인정보 없음). 로그인 여부와 무관.
 *  - heartbeat: 2분마다 + 탭 활성화 시 → '현재 접속'(5분 창)·'오늘 방문자' 산출.
 *  - PWA 설치: standalone 실행 감지를 heartbeat에 동봉(서버에서 래칫).
 *  - 페이지뷰: 라우트 전환마다 메뉴 키로 집계. 클릭: 핵심 버튼(위임 리스너, 클래스 규칙).
 *  - 전송은 큐 → 15초 배치 + pagehide 시 sendBeacon(이탈 유실 방지). 실패는 조용히 버림.
 */

const DEVICE_KEY = "saju_device_id";

function deviceId(): string {
  let id = localStorage.getItem(DEVICE_KEY);
  if (!id || !/^[0-9a-f-]{36}$/.test(id)) {
    id = crypto.randomUUID ? crypto.randomUUID()
      : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
          const r = (Math.random() * 16) | 0;
          return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
        });
    localStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

function platform(): "ios" | "android" | "desktop" | "other" {
  const ua = navigator.userAgent;
  if (/iphone|ipad|ipod/i.test(ua)) return "ios";
  if (/android/i.test(ua)) return "android";
  if (/windows|macintosh|linux/i.test(ua)) return "desktop";
  return "other";
}

function standalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (window.navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

type Ev = { kind: "page" | "click"; key: string; n?: number };
let queue: Ev[] = [];
let flushTimer: number | null = null;

function payload(): string {
  const body = { device_id: deviceId(), platform: platform(), standalone: standalone(), events: queue.slice(0, 20) };
  queue = queue.slice(20);
  return JSON.stringify(body);
}

function flush(useBeacon = false) {
  if (flushTimer) { window.clearTimeout(flushTimer); flushTimer = null; }
  const body = payload();
  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon("/api/usage/beat", new Blob([body], { type: "application/json" }));
    return;
  }
  fetch("/api/usage/beat", {
    method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true,
  }).catch(() => {});
}

function scheduleFlush() {
  if (flushTimer) return;
  flushTimer = window.setTimeout(() => { flushTimer = null; flush(); }, 15_000);
}

export function track(kind: "page" | "click", key: string) {
  const k = key.toLowerCase().replace(/[^a-z0-9:_-]/g, "").slice(0, 64);
  if (!k) return;
  const last = queue[queue.length - 1];
  if (last && last.kind === kind && last.key === k) last.n = (last.n || 1) + 1;  // 연속 중복은 합침
  else queue.push({ kind, key: k });
  scheduleFlush();
}

/** 라우트 → 메뉴 키(관리자 표시용) */
export function menuKey(pathname: string): string {
  if (pathname === "/") return "landing";
  const seg = pathname.split("/").filter(Boolean);
  if (seg[0] === "naming" && seg[1]) return `naming-${seg[1]}`;
  if (seg[0] === "snack" && seg[1]) return `snack-${seg[1]}`;
  return seg[0] || "landing";
}

// 핵심 버튼 클릭 규칙 — 클래스 기반 위임(페이지별 코드 수정 없이 전 메뉴 커버)
const CLICK_RULES: [string, string][] = [
  [".compat-cta", "cta"],            // 각 메뉴 실행 버튼(운세 보기·궁합 보기·길일 찾기·부적 발행…)
  [".chat-cta", "cta"],              // 사주상담 시작
  [".tr-cta", "cta"],                // 타로 시작
  [".sn-hub-cta", "cta"],            // 무료 테스트 시작
  [".explain-cta", "explain"],       // 해설 보기(무과금)
  [".qa-send", "question"],          // 추가 질문 전송(과금)
  [".reveal-cta-btn", "reveal"],     // 미리보기 전체 열람
  [".copy-btn", "answer-action"],    // 답변 액션바(복사·공유·PDF 묶음)
  [".bf-quick-btn", "quick-input"],  // 빠른입력 적용
  [".td-share-btn", "share-card"],   // 오늘의운세 공유카드 만들기
  [".vd-download", "download"],      // 영상/PDF/부적 다운로드·열기(공통 dock)
  [".am-dl", "download"],            // 부적 PNG 저장
  [".aa-video", "video"],            // 영상으로 보기
  [".report-btn", "report"],         // 종합 감정서
  [".app-install-btn", "install-guide"],  // 앱 설치(사이드바)
  [".install-fab", "install-fab"],   // 앱 설치(플로팅)
  [".pwa-escape", "inapp-escape"],   // 인앱 탈출 동의(크롬/사파리로 열기)
  [".consult-fab", "consult-fab"],   // 1:1 상담 플로팅
  [".charge-fab", "charge"],         // 충전 플로팅
  [".remember-check", "remember"],   // 내 사주정보 기억하기 토글
];

let started = false;

/** 앱 부트 시 1회 — heartbeat 루프 + 클릭 위임 리스너 */
export function startUsageTracking() {
  if (started) return;
  started = true;

  flush();                                        // 즉시 1회(방문 기록)
  window.setInterval(() => {
    if (document.visibilityState === "visible") flush();
  }, 120_000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") flush();
    else flush(true);                             // 백그라운드 전환 시 잔여 큐 beacon
  });
  window.addEventListener("pagehide", () => flush(true));

  document.addEventListener("click", (e) => {
    const t = e.target as Element | null;
    if (!t || !(t instanceof Element)) return;
    for (const [sel, key] of CLICK_RULES) {
      if (t.closest(sel)) {
        track("click", `${menuKey(location.pathname)}:${key}`);
        return;
      }
    }
  }, { capture: true, passive: true });
}
