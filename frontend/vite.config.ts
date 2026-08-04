import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // 로컬 백엔드 포트 오버라이드(.env.local: XEMBOI_API_PORT) — 기본 8008(saju_start.bat)
  const env = loadEnv(mode, process.cwd(), "");
  const apiPort = env.XEMBOI_API_PORT || "8008";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": `http://127.0.0.1:${apiPort}`,
      },
    },
  };
});
