@echo off
chcp 65001 > nul
title XEMBOI STOP
REM ============================================================
REM  xemboi (VN) STOP - isolated. Port 8009 + path D:\xemboi only.
REM  Child consultation worker (:8011) tree-killed via stop_port /T.
REM  Shared PG/Qdrant/Ollama/other tunnels preserved. No /IM global kill.
REM  Save as UTF-8 no-BOM + CRLF.
REM ============================================================
setlocal
set "SAJU_HOME=D:\xemboi"
set "SAJU_PORT=8009"
set "CF_SERVICE=cloudflared-xemboi"

echo ============================================================
echo    XEMBOI ^(VN^) STOP  ^(격리^)
echo ============================================================
echo.
echo [1/1] xemboi 백엔드^(:%SAJU_PORT%^) + 상담워커^(:8011 자식^) 격리 종료... ^(경로 한정: %SAJU_HOME%^)
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\_ops\stop_port.ps1" -Port %SAJU_PORT% -Proj "%SAJU_HOME%" -Token "uvicorn backend.app.main:app"

echo.
echo ============================================================
echo   [완료] xemboi 종료 ^(격리^). 공용 PG/Qdrant/Ollama/타 시스템 보존.
echo   ※ 전용 터널까지 내리려면^(선택^): sc stop %CF_SERVICE%   ^(관리자 권한^)
echo ============================================================
endlocal
pause > nul
