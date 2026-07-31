# 환경 점검 — 모든 외부 의존성이 정상 작동하는지 확인
# 사용: .\scripts\check_env.ps1

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

function Test-Item-Check {
    param([string]$Name, [scriptblock]$Check)
    Write-Host -NoNewline ("[{0,-25}] " -f $Name)
    try {
        $result = & $Check
        if ($result) {
            Write-Host "OK $result" -ForegroundColor Green
        } else {
            Write-Host "FAIL" -ForegroundColor Red
        }
    } catch {
        Write-Host "FAIL $_" -ForegroundColor Red
    }
}

Write-Host "== Saju Agent 환경 점검 ==" -ForegroundColor Cyan

Test-Item-Check "Python" { (& python --version 2>&1) }
Test-Item-Check "Node.js" { (& node --version 2>&1) }
Test-Item-Check "Git" { (& git --version 2>&1) }
Test-Item-Check "Docker" { (& docker --version 2>&1) }
Test-Item-Check "NVIDIA Driver" {
    $r = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1
    if ($LASTEXITCODE -eq 0) { $r -join " | " } else { $null }
}
Test-Item-Check "Ollama" {
    $r = & ollama --version 2>&1
    if ($LASTEXITCODE -eq 0) { $r } else { $null }
}

# 활성 가상환경
if (Test-Path ".venv\Scripts\python.exe") {
    & ".\.venv\Scripts\Activate.ps1"
    Test-Item-Check "venv Python" { (& python --version 2>&1) }
    Test-Item-Check "PyTorch CUDA" {
        & python -c "import torch; print(f'{torch.__version__} cuda={torch.cuda.is_available()}')" 2>&1
    }
    Test-Item-Check "sxtwl" { & python -c "import sxtwl; print('OK')" 2>&1 }
    Test-Item-Check "FastAPI" { & python -c "import fastapi; print(fastapi.__version__)" 2>&1 }
}

# 서비스 포트
Test-Item-Check "PostgreSQL :5432" {
    $r = Test-NetConnection -ComputerName localhost -Port 5432 -WarningAction SilentlyContinue
    if ($r.TcpTestSucceeded) { "listening" } else { $null }
}
Test-Item-Check "Redis :6379" {
    $r = Test-NetConnection -ComputerName localhost -Port 6379 -WarningAction SilentlyContinue
    if ($r.TcpTestSucceeded) { "listening" } else { $null }
}
Test-Item-Check "Qdrant :6333" {
    $r = Test-NetConnection -ComputerName localhost -Port 6333 -WarningAction SilentlyContinue
    if ($r.TcpTestSucceeded) { "listening" } else { $null }
}
Test-Item-Check "Ollama :11434" {
    $r = Test-NetConnection -ComputerName localhost -Port 11434 -WarningAction SilentlyContinue
    if ($r.TcpTestSucceeded) { "listening" } else { $null }
}

Write-Host "`n점검 완료." -ForegroundColor Cyan
