import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ChargeProvider } from "./components/ChargeModal";
import { ConsultationProvider } from "./components/ConsultationProvider";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "@fontsource-variable/noto-serif-kr";
import "./fonts-vi.css";
import "./styles.css";

// 초기 테마 적용(FOUC 방지) — useTheme 마운트 전에 data-theme 세팅
(() => {
  const saved = localStorage.getItem("saju_theme");
  const dark = saved === "dark" || (!saved && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();

// PWA Service Worker 등록 (정적 셸 캐싱 + 푸시)
// 새 SW가 활성화(controllerchange)되면 자동 1회 새로고침 → 프론트 변경 즉시 반영.
if ("serviceWorker" in navigator) {
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloaded || !hadController) return; // 최초 설치(이전 컨트롤러 없음)는 새로고침 불필요
    reloaded = true;
    window.location.reload();
  });
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      reg.update?.();
      setInterval(() => reg.update?.(), 60 * 60 * 1000); // 1시간마다 업데이트 체크
    }).catch(() => {});
  });
}

// GA4 유입 측정(P6) — VITE_GA4_ID(예: G-XXXXXXX) 설정 시에만 로드. 미설정이면 아무것도 안 함.
//   실 측정ID는 사용자가 frontend/.env.local 에 VITE_GA4_ID=... 로 넣고 재빌드하면 활성화된다.
const _ga4 = import.meta.env.VITE_GA4_ID as string | undefined;
if (_ga4) {
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${_ga4}`;
  document.head.appendChild(s);
  const w = window as any;
  w.dataLayer = w.dataLayer || [];
  w.gtag = function gtag() { w.dataLayer.push(arguments); };
  w.gtag("js", new Date());
  w.gtag("config", _ga4);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ChargeProvider>
        <ConsultationProvider>
          <App />
        </ConsultationProvider>
      </ChargeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
