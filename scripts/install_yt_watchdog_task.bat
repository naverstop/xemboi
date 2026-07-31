@echo off
REM ============================================================
REM  YouTube 와치독 Windows 예약작업 등록 (관리자 권한 필요)
REM  - 이 파일을 "관리자 권한으로 실행"하세요 (우클릭 → 관리자 권한)
REM  - 로그온 시 와치독 자동 기동 → 1주일 대기 → escalating(1/2/4주) → 월간 수집
REM  - 제거: schtasks /Delete /TN "SajuYTWatchdog" /F
REM ============================================================
chcp 65001 > nul
set "BAT=D:\saju_agent\scripts\start_yt_watchdog.bat"

REM 관리자 권한 확인
net session >nul 2>&1
if errorlevel 1 (
    echo [X] 관리자 권한이 아닙니다. 이 파일을 우클릭 → "관리자 권한으로 실행" 하세요.
    pause
    exit /b 1
)

schtasks /Create /TN "SajuYTWatchdog" /TR "cmd /c \"%BAT%\"" /SC ONLOGON /RL HIGHEST /F
if errorlevel 1 (
    echo [X] 예약작업 등록 실패
) else (
    echo [v] 예약작업 'SajuYTWatchdog' 등록 완료 ^(로그온 시 기동, 1주일 대기 후 수집^)
    echo     - 즉시 1회 테스트: schtasks /Run /TN "SajuYTWatchdog"
    echo     - 제거: schtasks /Delete /TN "SajuYTWatchdog" /F
)
schtasks /Query /TN "SajuYTWatchdog" /FO LIST 2>nul | findstr /i "TaskName Status Next"
pause
