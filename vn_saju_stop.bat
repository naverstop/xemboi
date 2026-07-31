@echo off
chcp 65001 > nul
REM ================================================================
REM  단독 정지 — VN 사주 (:8009 + 경로 D:\saju_vn 한정)
REM  ※ 공용 인프라(DB/Qdrant/Ollama) 및 사주1(:8008)/사주2 는 보존
REM ================================================================
setlocal
set "SAJU_HOME=D:\saju_vn"
set "SAJU_PORT=8009"
set "CF_SERVICE=cloudflared-saju-vn"

echo [1/1] VN 백엔드(:%SAJU_PORT%) 격리 종료... ^(경로 한정: %SAJU_HOME%^)
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\_ops\stop_port.ps1" -Port %SAJU_PORT% -Proj "%SAJU_HOME%" -Token "uvicorn backend.app.main:app"

echo.
echo [완료] VN(:8009) 종료. 공용 인프라 / 사주1 / 사주2 는 보존됩니다.
echo   ※ VN 터널까지 내리려면(선택): sc stop %CF_SERVICE%  ^(관리자^)
endlocal
pause
