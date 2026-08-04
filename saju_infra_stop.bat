@echo off
chcp 65001 > nul
title SAJU-INFRA STOP (shared)
REM ================================================================
REM  공동 정지 — 공용 인프라(Qdrant / Ollama) 종료
REM  ⚠️ 경고: 사주1/사주2/VN 중 하나라도 실행 중이면 정지하지 않는다(그 서비스가 깨짐).
REM      먼저 각 단독배치(saju_stop / saju2_stop / vn_saju_stop)로 앱을 모두 내린 뒤 실행.
REM  ※ PostgreSQL 서비스(postgresql-x64-17)는 윈도우 서비스라 기본 보존.
REM      내리려면(선택): net stop postgresql-x64-17  (관리자)
REM ================================================================
setlocal
echo 실행 중인 사주 서비스 포트 확인 (8008/8009/8010)...
powershell -NoProfile -Command "$busy=@(); foreach($p in 8008,8009,8010){ if(Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue){ $busy+=$p } }; if($busy.Count -gt 0){ Write-Host ('[!] 아직 실행 중: :' + ($busy -join ' :') + ' -> 공용 인프라 정지 중단'); exit 9 }; exit 0"
if errorlevel 9 (
    echo 서비스가 실행 중이라 공용 인프라를 정지하지 않습니다. 각 단독배치로 먼저 종료하세요.
    endlocal & pause & exit /b 1
)

echo Ollama / Qdrant 정지...
powershell -NoProfile -Command "Get-Process ollama -EA SilentlyContinue | Stop-Process -Force; Get-Process qdrant -EA SilentlyContinue | Stop-Process -Force"
echo [완료] 공용 인프라(Qdrant/Ollama) 정지. PostgreSQL 서비스는 보존.
endlocal
pause
