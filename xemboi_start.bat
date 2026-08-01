@echo off
chcp 65001 > nul
title XEMBOI :8009 (vi)
REM ########################### DO NOT MODIFY (guard) ###########################
REM  For any agent/human. NO CHANGES WITHOUT OPERATOR orion0321 APPROVAL.
REM   1) This is xemboi(VN) - SAJU_HOME=D:\xemboi, port 8009, DEFAULT_LOCALE=vi.
REM   2) Dedicated venv D:\xemboi\.venv (isolation). Do NOT reuse saju venv (cross-kill).
REM   3) Shared Qdrant:6333 / Ollama:11434 are LISTEN-checked ONLY (started by saju).
REM   4) Isolated stop: stop_port.ps1 -Port 8009 -Proj D:\xemboi (never /IM global kill).
REM   5) Save as UTF-8 no-BOM + CRLF. RUN ONCE.
REM ###############################################################################
REM  DB=PostgreSQL :5432 (xemboi_db) / Qdrant xemboi_corpus / Redis 6379/1
REM  API :8009 (+consultation 8011) / Domain: https://xemboi.io (cloudflared-xemboi)
setlocal enabledelayedexpansion
set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
set "SAJU_HOME=D:\xemboi"
set "SAJU_PORT=8009"
set "SAJU_CONSULTATION_PORT=8011"
set "SAJU_DOMAIN=xemboi.io"
set "CF_SERVICE=cloudflared-xemboi"
set "DB_SERVICE=postgresql-x64-17"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

set "DEV_RELOAD=1"
if "%DEV_RELOAD%"=="1" ( set "RELOAD_ARGS=--reload --reload-dir backend" ) else ( set "RELOAD_ARGS=" )

cd /d "%SAJU_HOME%"
if not exist "%SAJU_HOME%\.venv\Scripts\python.exe" (
    echo [X] venv missing: %SAJU_HOME%\.venv  ^(run pip install -e . first^)
    pause
    exit /b 1
)
if not exist "%SAJU_HOME%\logs" mkdir "%SAJU_HOME%\logs"

echo ============================================================
echo    XEMBOI ^(VN^) Agent  -  single window / isolated
echo    local http://127.0.0.1:%SAJU_PORT%   external https://%SAJU_DOMAIN%
echo ============================================================
echo.

REM [1/3] isolate-stop THIS agent only (port 8009 + path D:\xemboi; child :8011 tree-killed)
echo [1/3] xemboi 격리 정리 중... ^(경로 한정: %SAJU_HOME%^)
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\_ops\stop_port.ps1" -Port %SAJU_PORT% -Proj "%SAJU_HOME%" -Token "uvicorn backend.app.main:app"

REM [2/3] DB (idempotent start-only) / shared Qdrant+Ollama (LISTEN-check ONLY) / own tunnel
echo.
echo [2/3] DB / 공용 인프라^(Qdrant·Ollama^) 확인 / 터널...
sc query %DB_SERVICE% | findstr /i RUNNING > nul
if errorlevel 1 ( echo   [!] %DB_SERVICE% 미실행 - net start 시도 & net start %DB_SERVICE% >nul 2>nul ) else ( echo   [v] %DB_SERVICE% 실행 중 )
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 6333 -State Listen -EA SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 ( echo   [!] 공용 Qdrant:6333 미기동 - saju 등 공용 인프라를 먼저 기동하세요 ) else ( echo   [v] 공용 Qdrant:6333 확인 )
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 11434 -State Listen -EA SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 ( echo   [!] 공용 Ollama:11434 미기동 - saju 등 공용 인프라를 먼저 기동하세요 ) else ( echo   [v] 공용 Ollama:11434 확인 )
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 6379 -State Listen -EA SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 ( echo   [!] 공용 Redis:6379 미기동 - D:\_ops\redis\ensure_redis.bat 또는 START_master로 기동 ) else ( echo   [v] 공용 Redis:6379 확인 )
sc query %CF_SERVICE% | findstr /i RUNNING > nul
if errorlevel 1 ( echo   [!] %CF_SERVICE% 미등록/미실행 - 터널 등록 필요^(운영자^) ) else ( echo   [v] %CF_SERVICE% 실행 중 )

REM [3/3] backend foreground (serves vi frontend/dist + API; consultation :8011 spawned as child)
echo.
echo [3/3] 백엔드 :%SAJU_PORT% 기동 ^(DEV_RELOAD=%DEV_RELOAD%, locale=vi^) - 로그가 이 창에 출력됩니다.
echo       종료: Ctrl+C 또는 이 창 닫기
echo ------------------------------------------------------------
"%SAJU_HOME%\.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port %SAJU_PORT% %RELOAD_ARGS% --log-level info

echo ------------------------------------------------------------
echo [xemboi] 서버가 종료되었습니다. 아무 키나 누르면 창을 닫습니다.
endlocal
pause > nul
