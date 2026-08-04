@echo off
chcp 65001 > nul
title SAJU :8008
REM ########################### DO NOT MODIFY (guard) ###########################
REM  For any agent/human. Reverting these caused real outages (ASCII-only on purpose):
REM   *** NO CHANGES WITHOUT OPERATOR orion0321 (orion0321@gmail.com) APPROVAL. ***
REM       Report to the user and get explicit approval BEFORE editing anything here.
REM   1) Keep the [2/3] Ollama ready-wait + model warmup block.
REM      (uvicorn binding before model warm = cold-start import crash)
REM   2) Keep DEV_RELOAD=1 (dev reload) and the [GPU policy] block below.
REM   3) Launch via START_master Start-Process cmd /c (NOT bare start "title" bat).
REM   4) Save as UTF-8 no-BOM + CRLF (cmd parser codepage is cp949).
REM   5) RUN ONCE - never launch the same agent twice/concurrently.
REM      (a 2nd launch's stop_port kills the 1st instance = server goes down)
REM ###############################################################################
REM ============================================================
REM  saju_agent start (FastAPI backend) + Cloudflare Tunnel
REM  DB=PostgreSQL 17 :5432 (saju_db) / API :8008  진입점 backend.app.main:app
REM  도메인: https://saju.songstock.art  (cloudflared-saju 서비스)
REM  [표준] short(startshort.bat) 기준 - 단일 콘솔(같은 창 포그라운드) / 격리 실행
REM         이 창을 닫으면 이 서버만 종료됨(포트 8008 + 경로 한정, 타 에이전트 무영향)
REM         ※ Qdrant/Ollama 는 공용 인프라 - 숨김 백그라운드로 기동(미기동 시에만),
REM           콘솔 출력은 logs\qdrant.log / logs\ollama.log 로 통합 (별도 창 없음)
REM ============================================================
chcp 65001 > nul
setlocal enabledelayedexpansion

REM ###################### GPU 배치 정책 - 변경 금지 ######################
REM  [DO NOT REASSIGN - 2026-06-13]
REM    LLM Ollama = GPU1 RTX 5060 Ti 16GB.  임베딩/백엔드 = GPU1 RTX 5060 Ti 16GB.
REM    [2026-06-19 3050 8GB -> 5060Ti 16GB 교체완료. 이제 GPU0/GPU1 둘 다 동일 5060Ti라
REM     CUDA_DEVICE_ORDER=PCI_BUS_ID 필수 — 없으면 재부팅 시 GPU0<->GPU1 인덱스가
REM     뒤바뀌어 LLM(GPU1 지정)이 영상카드(PCI 02:00.0)를 잡고 FLUX OOM 사고.]
REM    GPU0 RTX 5060 Ti(PCI 02:00.0) 는 C:\shorts FLUX 영상생성 전용 - 한 PC에서 공유.
REM    Ollama 를 GPU0 으로 되돌리면 shorts FLUX 가 VRAM 부족으로 폭주
REM    악화되고 영상 파이프라인 장애. SAJU_LLM_GPU 값을 0 으로 바꾸지 말 것.
REM    변경 필요시 shorts 운영자 orion0321 와 GPU 배분 협의 후 수정.
REM ######################################################################
REM PCI 버스 순서로 CUDA 인덱스 고정(동일 5060Ti 2장 → 인덱스 뒤바뀜 방지). PCI0=GPU0(영상), PCI1=GPU1(LLM).
set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
set "SAJU_LLM_GPU=1"
set "SAJU_EMBED_GPU=1"
set "CUDA_VISIBLE_DEVICES=%SAJU_EMBED_GPU%"
set "SAJU_HOME=D:\saju_agent"
set "SAJU_PORT=8008"
set "SAJU_DOMAIN=saju.songstock.art"
set "CF_SERVICE=cloudflared-saju"
set "CF_TUNNEL=saju-tunnel"
set "DB_SERVICE=postgresql-x64-17"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

REM ── DevOps 토글: DEV_RELOAD 1=소스 자동반영(--reload) / 0=고정(운영전용) ──
set "DEV_RELOAD=1"
if "%DEV_RELOAD%"=="1" ( set "RELOAD_ARGS=--reload --reload-dir backend" ) else ( set "RELOAD_ARGS=" )

cd /d "%SAJU_HOME%"
if not exist "%SAJU_HOME%\.venv\Scripts\python.exe" (
    echo [X] venv missing: %SAJU_HOME%\.venv
    pause
    exit /b 1
)

echo ============================================================
echo    Saju Agent  -  단일창/격리 실행
echo    로컬 http://127.0.0.1:%SAJU_PORT%   외부 https://%SAJU_DOMAIN%
echo ============================================================
echo.

REM [1/3] 이 에이전트만 격리 종료 (포트 %SAJU_PORT% + 경로 %SAJU_HOME% 한정, 자기 자신 제외)
echo [1/3] 기존 saju 프로세스 격리 정리 중... ^(경로 한정: %SAJU_HOME%^)
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\_ops\stop_port.ps1" -Port %SAJU_PORT% -Proj "%SAJU_HOME%" -Token "uvicorn backend.app.main:app"
if not exist "%SAJU_HOME%\logs" mkdir "%SAJU_HOME%\logs"

REM [2/3] DB / Qdrant / Ollama / 터널 서비스 확인
echo.
echo [2/3] DB / Qdrant / Ollama / Cloudflare 터널 확인...
sc query %DB_SERVICE% | findstr /i RUNNING > nul
if errorlevel 1 ( echo   [!] %DB_SERVICE% 미실행 - net start 시도 & net start %DB_SERVICE% >nul 2>nul ) else ( echo   [v] %DB_SERVICE% 실행 중 )

REM -- Qdrant :6333 (공용 인프라 - 미기동 시에만 숨김창 기동, 출력은 logs\qdrant.log) --
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 6333 -State Listen -EA SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
    if exist "%SAJU_HOME%\infra\qdrant\qdrant.exe" (
        echo   - Qdrant 시작 ^(:6333, 숨김창, 로그=logs\qdrant.log^)...
        powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c %SAJU_HOME%\infra\qdrant\qdrant.exe >> %SAJU_HOME%\logs\qdrant.log 2>&1' -WorkingDirectory '%SAJU_HOME%\infra\qdrant' -WindowStyle Hidden"
        powershell -NoProfile -Command "foreach($i in 1..20){ if(Get-NetTCPConnection -LocalPort 6333 -State Listen -EA SilentlyContinue){exit 0}; Start-Sleep 1 }; exit 1" >nul 2>&1
        if errorlevel 1 ( echo   [!] Qdrant 기동 확인 실패 - logs\qdrant.log 확인 ) else ( echo   [v] Qdrant 기동 확인 ^(:6333^) )
    ) else ( echo   [X] qdrant.exe 없음 )
) else ( echo   [v] Qdrant 실행 중 ^(:6333^) )

REM -- Ollama :11434 (LLM 추론 GPU1(5060Ti) — 상단 [GPU 배치 정책] 참조, GPU0은 shorts FLUX 전용, 미기동 시에만 숨김창 기동, 출력은 logs\ollama.log) --
set "OLLAMA_MODELS=%SAJU_HOME%\infra\ollama\models"
set "OLLAMA_HOST=127.0.0.1:11434"
set "OLLAMA_KEEP_ALIVE=-1"
REM Vulkan 차단 - ollama가 Vulkan 경유로 GPU0(shorts FLUX 전용)을 잡는 것 방지 (CUDA 로 GPU1(5060Ti)만 사용)
set "OLLAMA_VULKAN=0"
REM 16GB 활용: flash attention + KV 캐시 q8 양자화 → KV VRAM 절반(num_ctx 8K에 exaone+qwen+임베딩 공존).
REM   (KV q8는 flash attention 활성 전제. 8GB 3050 시절엔 불가, 5060Ti 16GB 교체로 적용.)
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_KV_CACHE_TYPE=q8_0"
REM qwen3:14b: np3 + KV q4_0 (verified 2026-07-22: 3x 11.5k-tok concurrent, VRAM peak 14.1GB, no spill).
set "OLLAMA_NUM_PARALLEL=6"
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 11434 -State Listen -EA SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
    if exist "%SAJU_HOME%\infra\ollama\ollama.exe" (
        echo   - Ollama 시작 ^(:11434, 추론 GPU%SAJU_LLM_GPU%, 숨김창, 로그=logs\ollama.log^)...
        REM [변경금지] ollama = GPU1 고정(SAJU_LLM_GPU=1). GPU0 은 shorts FLUX 전용 — 상단 [GPU 배치 정책] 블록 참조.
        set "CUDA_VISIBLE_DEVICES=%SAJU_LLM_GPU%"
        powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c %SAJU_HOME%\infra\ollama\ollama.exe serve >> %SAJU_HOME%\logs\ollama.log 2>&1' -WindowStyle Hidden"
        set "CUDA_VISIBLE_DEVICES=%SAJU_EMBED_GPU%"
        powershell -NoProfile -Command "foreach($i in 1..20){ if(Get-NetTCPConnection -LocalPort 11434 -State Listen -EA SilentlyContinue){exit 0}; Start-Sleep 1 }; exit 1" >nul 2>&1
        if errorlevel 1 ( echo   [!] Ollama 기동 확인 실패 - logs\ollama.log 확인 ) else ( echo   [v] Ollama 기동 확인 ^(:11434^) )
    ) else ( echo   [X] ollama.exe 없음 )
) else ( echo   [v] Ollama 실행 중 ^(:11434^) )

REM -- Ollama "응답 가능(query-ready)" 대기 (2026-06-13) --------------------------
REM   포트 열림(:11434 LISTEN)만으로는 모델 워밍업 전이라, 콜드 기동 시 saju 가
REM   ollama 에 연결하다 실패해 죽는 레이스가 있었다. API 응답 + 모델 워밍업까지
REM   확인한 뒤에 uvicorn 을 띄운다. (모델명은 .env 의 OLLAMA_MODEL 과 일치 유지)
set "SAJU_OLLAMA_MODEL=qwen3:14b"
REM [필수] 워밍업 num_ctx 는 config.py ollama_num_ctx 와 반드시 동일하게 유지할 것.
REM   불일치 시 ollama 가 다른 ctx 의 러너를 새로 띄우려다 VRAM 부족으로 교착 → 워밍업 무한대기
REM   (2026-07-23 장애: 상주 ctx 16384 vs 워밍업 기본 4096 → 여유 3.2GB로 재적재 불가 → 기동 실패).
set "SAJU_OLLAMA_NUM_CTX=24576"
echo   - Ollama API 응답 대기 중...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try{ if((Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:11434/api/tags').StatusCode -eq 200){$ok=$true;break} }catch{}; Start-Sleep 2 }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 ( echo   [!] Ollama API 응답 대기 시간초과 - logs\ollama.log 확인 ) else ( echo   [v] Ollama API 응답 가능 )
echo   - Ollama 모델 워밍업 중 ^(%SAJU_OLLAMA_MODEL%, 최초 로드 시 수십초 소요^)...
powershell -NoProfile -Command "$b=@{model='%SAJU_OLLAMA_MODEL%';prompt='ping';stream=$false;options=@{num_predict=1;num_ctx=%SAJU_OLLAMA_NUM_CTX%}} | ConvertTo-Json -Compress; try{ Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post -Body $b -ContentType 'application/json' -TimeoutSec 180 | Out-Null; exit 0 }catch{ exit 1 }"
if errorlevel 1 ( echo   [!] 모델 워밍업 실패/시간초과 - 기동은 계속 진행 ) else ( echo   [v] Ollama 모델 워밍업 완료 ^(응답 가능^) )

sc query %CF_SERVICE% | findstr /i RUNNING > nul
if errorlevel 1 ( echo   [!] %CF_SERVICE% 미실행 - sc start 시도 & sc start %CF_SERVICE% >nul 2>nul ) else ( echo   [v] %CF_SERVICE% 실행 중 )

REM [FE] frontend auto-build (only when src changed) - serve latest UI on startup
REM   If frontend\src is newer than dist, run vite build. Non-fatal: keep old dist on failure.
echo.
echo [FE] frontend build check (refresh frontend\dist)...
set "PATH=C:\Program Files\nodejs;D:\nodejs;%PATH%"
powershell -NoProfile -Command "$d=Get-Item '%SAJU_HOME%\frontend\dist\index.html' -EA SilentlyContinue; if(-not $d){exit 0}; $s=Get-ChildItem '%SAJU_HOME%\frontend\src','%SAJU_HOME%\frontend\index.html','%SAJU_HOME%\frontend\package.json','%SAJU_HOME%\frontend\vite.config.ts' -Recurse -File -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($s -and $s.LastWriteTime -gt $d.LastWriteTime){exit 0}else{exit 1}"
if errorlevel 1 ( echo   [v] frontend dist up-to-date - skip build & goto :fe_done )
echo   - source change detected - vite build ^(first/large change: tens of seconds^)...
pushd "%SAJU_HOME%\frontend"
call npm run build
if errorlevel 1 ( echo   [!] frontend build FAILED - keep existing dist, continue ) else ( echo   [v] frontend build done - dist updated )
popd
:fe_done

REM [3/3] 백엔드를 '이 창'에서 포그라운드 실행 (로그 실시간 / 창 닫으면 이 서버만 종료)
echo.
echo [3/3] uvicorn :%SAJU_PORT% 기동 (DEV_RELOAD=%DEV_RELOAD%) - 로그가 이 창에 출력됩니다.
echo       종료: Ctrl+C 또는 이 창 닫기  (Qdrant/Ollama 는 백그라운드 유지)
echo ------------------------------------------------------------
"%SAJU_HOME%\.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port %SAJU_PORT% %RELOAD_ARGS% --log-level info

echo ------------------------------------------------------------
echo [saju] 서버가 종료되었습니다. 아무 키나 누르면 창을 닫습니다.
endlocal
pause > nul
