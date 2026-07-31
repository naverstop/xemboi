# saju_agent — 운영정보

> 최종 점검: 2026-06-22 · 서버: SONGS_SERVER · ⚠️ DB는 **PostgreSQL 17** (MySQL 미사용)
> 2026-06-22 갱신: 포트 8000→**8008**, GPU RTX 3050→**5060 Ti 16GB ×2**(6/19 교체) 반영.

| 항목 | 값 |
|---|---|
| 역할 | 사주 분석 백엔드 |
| 스택 | Python 3.11.9 + venv / **FastAPI (uvicorn)** |
| 홈 | `D:\saju_agent` |
| 시작 배치 | `D:\saju_agent\saju_start.bat` |
| 진입점 | `uvicorn backend.app.main:app --host 127.0.0.1 --port 8008` |
| 웹/포트 | FastAPI **:8008** (saju_start.bat `SAJU_PORT=8008`) |
| GPU | **RTX 5060 Ti 16GB ×2** (2026-06-19 3050→교체). 백엔드/임베딩·LLM(Ollama)=**GPU1**, GPU0=`C:\shorts` FLUX 영상생성 전용. ⚠️ **`CUDA_DEVICE_ORDER=PCI_BUS_ID` 필수**(동일 카드 2장이라 미설정 시 재부팅 때 GPU0↔1 인덱스 뒤바뀜→LLM이 FLUX 카드 점유·OOM 사고) |

## DB
| 엔진 | **PostgreSQL 17** |
|---|---|
| 서비스명 | `postgresql-x64-17` |
| 포트 | 5432 |
| DB명 | `saju_db` |
| datadir | `D:\pgsql\17\data` |
| 접속 | `postgresql+psycopg://saju:****@127.0.0.1:5432/saju_db` |
| 마이그레이션 | `alembic upgrade head` (head=`20260602_0001_startup_ddl`) |

> 과거 `MySQL_Saju(3308)` 잔재는 폐기 → `F:\backup\_obsolete_saju_mysql\`로 격리됨.

## 환경변수 (saju_start.bat)
- `SAJU_PORT=8008` (uvicorn `--port`)
- `CUDA_DEVICE_ORDER=PCI_BUS_ID` ⚠️ 필수 — 동일 5060Ti 2장의 인덱스 고정
- `SAJU_LLM_GPU=1` (Ollama LLM) / `SAJU_EMBED_GPU=1` (임베딩·백엔드) / `CUDA_VISIBLE_DEVICES=%SAJU_EMBED_GPU%`
  - GPU0(PCI 02:00.0)=shorts FLUX 전용 — `SAJU_LLM_GPU`를 0으로 바꾸지 말 것(FLUX OOM). 변경 시 shorts 운영자(orion0321) 협의.
- `SAJU_HOME=D:\saju_agent`
- `SAJU_DB_HOST=127.0.0.1` / `SAJU_DB_PORT=5432`
- `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`

## 경로/파일
- `.env`: `D:\saju_agent\.env` (ANTHROPIC_API_KEY / OPENAI_API_KEY / TAVILY_API_KEY / JWT_SECRET / APP_PORT=8008)
- venv: `D:\saju_agent\.venv` (psycopg 포함, `backend\requirements.txt`)
- 로그: `D:\saju_agent\logs`

## 백업
- DB: `F:\backup\db\saju\YYYYMMDD\saju_db.sql.gz` (**pg_dump**, 매일 04:00)
- 설정: `F:\backup\config\saju\`

## 스모크 점검
```powershell
sc query postgresql-x64-17 | findstr RUNNING
cd D:\saju_agent; .\saju_start.bat
# http://127.0.0.1:8008/docs 접속 확인 + nvidia-smi GPU1 점유
```
