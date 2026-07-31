@echo off
REM ============================================================
REM  Saju Agent STOP  -  격리 종료
REM  [표준] short식 - 비상승 / 앱 서버(:8008)만 종료
REM  ※ 포트 8008 + 경로 D:\saju_agent 한정 → 타 에이전트 무영향
REM  ※ DB(PostgreSQL) / Qdrant / Ollama / 터널(cloudflared-saju)은 보존(공유 인프라)
REM ============================================================
chcp 65001 > nul
setlocal enabledelayedexpansion

set "SAJU_HOME=D:\saju_agent"
set "SAJU_PORT=8008"
set "CF_SERVICE=cloudflared-saju"

echo ============================================================
echo    Saju Agent STOP  (격리)
echo ============================================================
echo.

echo [1/1] saju 백엔드(:%SAJU_PORT%) 격리 종료 중... ^(경로 한정: %SAJU_HOME%^)
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\_ops\stop_port.ps1" -Port %SAJU_PORT% -Proj "%SAJU_HOME%" -Token "uvicorn backend.app.main:app"

echo.
echo ============================================================
echo   [완료] saju 백엔드 종료 (격리)
echo   PostgreSQL / Qdrant / Ollama / 터널 / 타 에이전트는 보존됩니다.
echo   ※ 터널까지 내리려면(선택): sc stop %CF_SERVICE%   ^(관리자 권한^)
echo ============================================================
endlocal
pause
