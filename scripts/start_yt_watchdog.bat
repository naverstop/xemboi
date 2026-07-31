@echo off
REM ============================================================
REM  YouTube 자막 수집 와치독 (차단 방지 · 자동 재색인 · 정기수집)
REM
REM  동작:
REM   1) 초기 1주일 대기(차단 IP 자연 회복 대기)
REM   2) probe로 회복 확인. 여전히 차단이면 1주 → 2주 → 4주 escalating 재시도
REM   3) 회복되면 자막 수집(신규 10개마다 10분 휴식) + 자동 재색인(ingest_rag)
REM   4) 이후 30일마다 정기 수집(새로 올라온 영상 반영) + 자동 재색인 (영구 반복)
REM   - 자막 없는 영상은 faster-whisper STT(설치돼 있으면), 없으면 건너뜀
REM
REM  사용: 이 배치를 실행하면 1주일 뒤부터 수집을 시작합니다.
REM  프록시(IP우회) 사용 시 아래 YT_PROXY 주석 해제 후 주소 입력.
REM ============================================================
chcp 65001 > nul
set "SAJU_HOME=D:\saju_agent"
cd /d "%SAJU_HOME%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%SAJU_HOME%"
set "HF_HOME=%SAJU_HOME%\infra\hf_cache"
REM 임베딩/STT GPU = 5060(GPU0)
set "CUDA_VISIBLE_DEVICES=0"

REM --- 프록시(IP 우회) 사용 시 주석 해제 ---
REM set "YT_PROXY=--proxy socks5://127.0.0.1:1080"

echo [start_yt_watchdog] 1주일 대기 후 자막 수집을 시작합니다. (Ctrl+C 로 종료)
"%SAJU_HOME%\.venv\Scripts\python.exe" -u scripts\yt_watchdog.py ^
  --initial-wait-days 7 ^
  --escalate-weeks 1,2,4 ^
  --monthly-days 30 ^
  --batch-size 10 ^
  --batch-sleep-min 10 %YT_PROXY%
pause
