# Saju Agent — 가상환경 생성 및 의존성 설치
# 사용: .\scripts\setup_venv.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

Write-Host "== Saju Agent 가상환경 셋업 ==" -ForegroundColor Cyan

# Python 버전 확인
$py = & python --version 2>&1
if (-not ($py -match "Python 3\.(11|12)")) {
    Write-Error "Python 3.11 또는 3.12 필요. 현재: $py"
    exit 1
}
Write-Host "Python OK: $py"

# venv 생성
if (-not (Test-Path ".venv")) {
    Write-Host "`n.venv 생성 중..." -ForegroundColor Yellow
    & python -m venv .venv
}

# 활성화
& ".\.venv\Scripts\Activate.ps1"

# pip 업그레이드
Write-Host "`npip 업그레이드..." -ForegroundColor Yellow
& python -m pip install --upgrade pip setuptools wheel

# 기본 의존성
Write-Host "`n기본 의존성 설치 (Phase 1~3)..." -ForegroundColor Yellow
& pip install -e ".[dev]"

Write-Host "`n== 완료 ==" -ForegroundColor Green
Write-Host "다음 단계:"
Write-Host "  1) PyTorch CUDA:   .\scripts\install_torch_cuda.ps1"
Write-Host "  2) 인프라 기동:    docker compose -f infra\docker\docker-compose.yml up -d"
Write-Host "  3) Ollama 모델:    ollama pull qwen2.5:7b-instruct-q4_K_M"
Write-Host "  4) 환경 점검:      .\scripts\check_env.ps1"
