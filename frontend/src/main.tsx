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
import i18n from "./i18n";

// 초기 테마 적용(FOUC 방지) — useTheme 마운트 전에 data-theme 세팅
(() => {
  const saved = localStorage.getItem("saju_theme");
  const dark = saved === "dark" || (!saved && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();

// 초기 로케일 반영 — 첫 페인트 전에 <html lang> + 문서 타이틀(브랜드) 세팅(언어 깜빡임 방지)
(() => {
  const loc = i18n.language || "ko";
  document.documentElement.lang = loc;
  const brand = i18n.t("brand");
  if (brand) document.title = brand;
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
