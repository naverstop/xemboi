@echo off
chcp 65001 > nul
title SAJU-INFRA (shared: DB / Qdrant / Ollama GPU1)
REM ############### DO NOT MODIFY without operator orion0321 approval ###############
REM  Save as UTF-8 no-BOM + CRLF. ASCII-only guard on purpose.
REM ################################################################################
REM ================================================================
REM  공동배치 (SHARED INFRA) — 사주1 + 사주2 + VN사주 공용 자원만 기동
REM   - PostgreSQL 서비스(:5432, DB명은 서비스별 분리) / Qdrant :6333 / Ollama :11434(GPU1)
REM   - 앱(uvicorn/frontend/tunnel)은 각 '단독배치'가 담당 (saju_start / saju2_start / vn_saju_start)
REM   - 멱등: 이미 떠 있으면 재기동하지 않음 → 중복 로딩에 의한 GPU1 충돌 원천 차단(핵심)
REM   - 각 단독배치가 이 파일을 call 로 호출(공용 확보) 후 자기 앱만 띄운다
REM   - saju_start.bat(사주1, 마스터)은 수정하지 않음. 물리 경로만 SHARED_HOME 로 공유
REM ================================================================
setlocal enabledelayedexpansion

REM ===== 공용 인프라 물리 경로 (중립화 목표: D:\saju_shared. 현재는 마스터 밑을 공유) =====
set "SHARED_HOME=D:\saju_agent"
set "DB_SERVICE=postgresql-x64-17"

REM ###################### GPU 배치 정책 - 변경 금지 ######################
REM  Ollama LLM = GPU1(RTX 5060 Ti 16GB). GPU0(PCI 02:00.0) = C:\shorts FLUX 전용.
REM  동일 카드 2장 → CUDA_DEVICE_ORDER=PCI_BUS_ID 필수(재부팅 시 인덱스 뒤바뀜 방지).
REM  SAJU_LLM_GPU 를 0 으로 바꾸면 FLUX OOM. 변경 시 orion0321 협의.
REM ######################################################################
set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
set "SAJU_LLM_GPU=1"
set "OLLAMA_MODELS=%SHARED_HOME%\infra\ollama\models"
set "OLLAMA_HOST=127.0.0.1:11434"
set "OLLAMA_KEEP_ALIVE=-1"
REM Vulkan 차단 - GPU0(FLUX) 오점유 방지. flash attn + KV q8 → 16GB 에 다모델 공존.
set "OLLAMA_VULKAN=0"
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_KV_CACHE_TYPE=q8_0"

if not exist "%SHARED_HOME%\logs" mkdir "%SHARED_HOME%\logs"
echo [INFRA] 공용 자원 확인/기동 (멱등)...

REM -- PostgreSQL (공용 DB 서버; DB명은 서비스별 분리: saju_db / saju2_db / saju_vn_db) --
sc query %DB_SERVICE% | findstr /i RUNNING > nul
if errorlevel 1 ( echo   [!] %DB_SERVICE% 미실행 - net start & net start %DB_SERVICE% >nul 2>nul ) else ( echo   [v] %DB_SERVICE% 실행 중 ^(:5432^) )

REM -- Qdrant :6333 (공용; 컬렉션은 서비스별 분리: saju_corpus / saju2_corpus / saju_vn_corpus) --
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 6333 -State Listen -EA SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
    if exist "%SHARED_HOME%\infra\qdrant\qdrant.exe" (
        echo   - Qdrant 기동 ^(:6333, 숨김, logs\qdrant.log^)...
        powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c %SHARED_HOME%\infra\qdrant\qdrant.exe >> %SHARED_HOME%\logs\qdrant.log 2>&1' -WorkingDirectory '%SHARED_HOME%\infra\qdrant' -WindowStyle Hidden"
        powershell -NoProfile -Command "foreach($i in 1..20){ if(Get-NetTCPConnection -LocalPort 6333 -State Listen -EA SilentlyContinue){exit 0}; Start-Sleep 1 }; exit 1" >nul 2>&1
        if errorlevel 1 ( echo   [!] Qdrant 기동 확인 실패 - logs\qdrant.log ) else ( echo   [v] Qdrant 기동 확인 ^(:6333^) )
    ) else ( echo   [X] qdrant.exe 없음: %SHARED_HOME%\infra\qdrant )
) else ( echo   [v] Qdrant 실행 중 ^(:6333, 재기동 안 함^) )

REM -- Ollama :11434 (공용, GPU1) — 이미 떠 있으면 절대 재기동 안 함(중복 = GPU1 충돌) --
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 11434 -State Listen -EA SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
    if exist "%SHARED_HOME%\infra\ollama\ollama.exe" (
        echo   - Ollama 기동 ^(:11434, 추론 GPU%SAJU_LLM_GPU%, 숨김, logs\ollama.log^)...
        set "CUDA_VISIBLE_DEVICES=%SAJU_LLM_GPU%"
        powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c %SHARED_HOME%\infra\ollama\ollama.exe serve >> %SHARED_HOME%\logs\ollama.log 2>&1' -WindowStyle Hidden"
        powershell -NoProfile -Command "foreach($i in 1..30){ if(Get-NetTCPConnection -LocalPort 11434 -State Listen -EA SilentlyContinue){exit 0}; Start-Sleep 1 }; exit 1" >nul 2>&1
        if errorlevel 1 ( echo   [!] Ollama 기동 확인 실패 - logs\ollama.log ) else ( echo   [v] Ollama 기동 확인 ^(:11434^) )
    ) else ( echo   [X] ollama.exe 없음: %SHARED_HOME%\infra\ollama )
) else ( echo   [v] Ollama 실행 중 ^(:11434, 재기동 안 함^) )

REM -- Ollama API 응답 대기(공용). 모델 워밍업은 각 단독배치가 자기 모델로 수행 --
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try{ if((Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:11434/api/tags').StatusCode -eq 200){$ok=$true;break} }catch{}; Start-Sleep 2 }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 ( echo   [!] Ollama API 무응답 - logs\ollama.log ) else ( echo   [v] Ollama API 응답 가능 )

echo [INFRA] 공용 자원 준비 완료. 단독배치를 실행하세요 ^(saju_start / vn_saju_start / saju2_start^).
endlocal
