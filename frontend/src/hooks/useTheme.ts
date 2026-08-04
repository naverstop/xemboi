/** 다크/라이트 테마 토글 훅.
 * - localStorage("saju_theme") 우선 → 없으면 기본 light(화이트).
 *   (OS 다크 설정을 자동으로 따르지 않음 — 기본 로딩은 항상 화이트)
 * - html[data-theme] 속성으로 CSS 변수 전환.
 */
import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

function initialTheme(): Theme {
  const saved = localStorage.getItem("saju_theme");
  if (saved === "light" || saved === "dark") return saved;
  // 저장된 선택이 없으면 기본 화이트(light). OS 다크 설정을 자동 추종하지 않음.
  return "light";
}

export function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#0b1620" : "#0d9488");
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("saju_theme", theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return { theme, toggle, setTheme };
}
