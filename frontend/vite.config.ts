import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 사주 백엔드(uvicorn)는 saju_start.bat 에서 :8008 로 기동됨
      "/api": "http://127.0.0.1:8008",
    },
  },
});
