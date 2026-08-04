@echo off
chcp 65001 > nul
title SAJU-VN :8009 (vi)
REM ############### DO NOT MODIFY without operator orion0321 approval ###############
REM  Save as UTF-8 no-BOM + CRLF.
REM ################################################################################
REM ================================================================
REM  단독배치 (STANDALONE) — VN 사주 (베트남어, locale=vi)
REM   격리(전용): 폴더 D:\saju_vn / 포트 8009 / DB saju_vn_db / Qdrant 컬렉션 saju_vn_corpus
REM               / 터널 cloudflared-saju-vn / frontend dist
REM   공용 재사용: DB서버·Qdrant·Ollama(GPU1, qwen3:14b) → saju_infra_start.bat 이 담당(멱등)
REM   단독 실행/정지: 이 창을 닫으면 VN(:8009)만 종료. 사주1(:8008)/사주2 무영향.
REM   ※ 공용 Ollama 는 이미 떠 있으면 재사용(중복 로딩 금지=GPU1 충돌 방지)
REM ================================================================
setlocal enabledelayedexpansion

REM ===== VN 전용(격리) 파라미터 =====
set "SAJU_HOME=D:\saju_vn"
set "SAJU_PORT=8009"
set "SAJU_LOCALE=vi"
set "SAJU_DOMAIN=xemboi.io"
set "CF_SERVICE=cloudflared-xemboi"
set "SAJU_OLLAMA_MODEL=qwen3:14b"

REM ===== 공용 인프라 위치(단독배치가 call 로 확보) =====
set "SHARED_HOME=D:\saju_agent"

REM ===== GPU: 백엔드/임베딩 GPU1 (LLM은 공용 Ollama가 GPU1 담당) — 정책 변경 금지 =====
set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
set "SAJU_EMBED_GPU=1"
set "CUDA_VISIBLE_DEVICES=%SAJU_EMBED_GPU%"

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "DEV_RELOAD=1"
if "%DEV_RELOAD%"=="1" ( set "RELOAD_ARGS=--reload --reload-dir backend" ) else ( set "RELOAD_ARGS=" )

cd /d "%SAJU_HOME%"
if not exist "%SAJU_HOME%\.venv\Scripts\python.exe" ( echo [X] venv 없음: %SAJU_HOME%\.venv & pause & exit /b 1 )
if not exist "%SAJU_HOME%\logs" mkdir "%SAJU_HOME%\logs"

echo ============================================================
echo    VN 사주 (locale=vi)  -  단독창/격리 실행
echo    로컬 http://127.0.0.1:%SAJU_PORT%   외부 https://%SAJU_DOMAIN%
echo ============================================================

REM [1/4] VN 인스턴스만 격리 종료 (포트 8009 + 경로 D:\saju_vn 한정; 사주1/사주2 무영향)
echo [1/4] 기존 VN 프로세스 격리 정리...
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\_ops\stop_port.ps1" -Port %SAJU_PORT% -Proj "%SAJU_HOME%" -Token "uvicorn backend.app.main:app"

REM [2/4] 공용 인프라 확보 (멱등 — 이미 떠 있으면 재사용)
echo [2/4] 공용 인프라 확보 (saju_infra_start.bat)...
call "%SHARED_HOME%\saju_infra_start.bat"

REM [3/4] VN 모델 워밍업 (공용 Ollama 의 qwen3:14b)
echo [3/4] qwen3:14b 워밍업 (최초 로드 시 수십초)...
powershell -NoProfile -Command "$b=@{model='%SAJU_OLLAMA_MODEL%';prompt='ping';stream=$false;options=@{num_predict=1}} | ConvertTo-Json -Compress; try{ Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post -Body $b -ContentType 'application/json' -TimeoutSec 180 | Out-Null; exit 0 }catch{ exit 1 }"
if errorlevel 1 ( echo   [!] 워밍업 실패/시간초과 - 기동 계속 ) else ( echo   [v] qwen3:14b 워밍업 완료 )

REM [FE] VN frontend build (src 변경 시에만)
set "PATH=C:\Program Files\nodejs;D:\nodejs;%PATH%"
powershell -NoProfile -Command "$d=Get-Item '%SAJU_HOME%\frontend\dist\index.html' -EA SilentlyContinue; if(-not $d){exit 0}; $s=Get-ChildItem '%SAJU_HOME%\frontend\src','%SAJU_HOME%\frontend\index.html','%SAJU_HOME%\frontend\package.json','%SAJU_HOME%\frontend\vite.config.ts' -Recurse -File -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($s -and $s.LastWriteTime -gt $d.LastWriteTime){exit 0}else{exit 1}"
if errorlevel 1 ( echo   [v] frontend dist 최신 - build 생략 & goto :fe_done )
echo   - frontend 변경 감지 - vite build...
pushd "%SAJU_HOME%\frontend"
call npm run build
if errorlevel 1 ( echo   [!] frontend build 실패 - 기존 dist 유지 ) else ( echo   [v] frontend build 완료 )
popd
:fe_done

REM [4/4] uvicorn :8009 (locale=vi) 포그라운드 (창 닫으면 VN 만 종료)
echo [4/4] uvicorn :%SAJU_PORT% (locale=vi) 기동 - 종료: Ctrl+C 또는 이 창 닫기
echo ------------------------------------------------------------
"%SAJU_HOME%\.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port %SAJU_PORT% %RELOAD_ARGS% --log-level info

echo ------------------------------------------------------------
echo [VN 사주] 서버 종료됨. 공용 인프라/사주1/사주2 는 유지됩니다.
endlocal
pause > nul
