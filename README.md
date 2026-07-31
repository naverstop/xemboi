# Saju Agent — 사주 상담 LLM 챗봇

> Qwen2.5-7B + RAG + QLoRA / Windows 11 네이티브 / 자체 호스팅

## 문서
- [시스템 설계](SAJ_agent_시스템%20설계.md)
- [구현 계획서](SAJU_Agent_구현계획.md)

## 빠른 시작 (Phase 0 환경 셋업)

### 1) 사전 설치 (수동)
관리자 권한 PowerShell에서 다음을 먼저 설치하세요:

| 항목 | 다운로드 / 명령 |
|---|---|
| Python 3.11 | https://www.python.org/downloads/ (PATH 추가 체크) |
| Node.js 20 LTS | https://nodejs.org/ |
| Git for Windows | https://git-scm.com/download/win |
| NVIDIA Driver (최신) | https://www.nvidia.com/Download/index.aspx |
| CUDA Toolkit 12.4+ | https://developer.nvidia.com/cuda-downloads |
| Docker Desktop | https://www.docker.com/products/docker-desktop/ (WSL2 백엔드) |
| PostgreSQL 16 | https://www.postgresql.org/download/windows/ |
| Ollama for Windows | https://ollama.com/download/windows |

### 2) 프로젝트 셋업
```powershell
# 가상환경 생성
.\scripts\setup_venv.ps1

# 가상환경 활성화
.\.venv\Scripts\Activate.ps1

# PyTorch CUDA 빌드 설치 (training extras 전에 먼저)
.\scripts\install_torch_cuda.ps1

# 인프라 컨테이너 기동 (Qdrant + Redis)
docker compose -f infra\docker\docker-compose.yml up -d

# Ollama 모델 다운로드 (~4.5GB)
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull bge-m3   # 임베딩 (선택, sentence-transformers로도 가능)
```

### 3) 동작 확인
```powershell
.\scripts\check_env.ps1
```

## 디렉토리 구조
```
backend/     # FastAPI (사주엔진, RAG, API)
frontend/    # Next.js
ml/          # 추론/학습/데이터 파이프라인
infra/       # Caddy, Cloudflare, Docker, NSSM
scripts/     # PowerShell 운영 스크립트
data/        # 원본/가공/OCR 결과 (git 제외)
학습자료/    # 사주 PDF 자료 (git 제외)
```

## 진행 단계
현재: **Phase 0 환경 셋업** 진행 중 → Phase 1 사주명식 엔진 → Phase 2 RAG+채팅 코어
# saju
