# PyTorch CUDA 12.4 빌드 설치 (Windows)
# 사용: .\scripts\install_torch_cuda.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "먼저 .\scripts\setup_venv.ps1 실행 필요"
    exit 1
}

& ".\.venv\Scripts\Activate.ps1"

Write-Host "== PyTorch CUDA 12.4 설치 ==" -ForegroundColor Cyan
Write-Host "다운로드 약 2.5GB, 시간 소요됩니다." -ForegroundColor Yellow

# CUDA 12.4 빌드 (RTX 3050 / 5060 Ti 모두 지원)
& pip install --index-url https://download.pytorch.org/whl/cu124 `
    torch torchvision torchaudio

Write-Host "`n== 검증 ==" -ForegroundColor Cyan
& python -c @"
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'CUDA version: {torch.version.cuda}')
    print(f'Device count: {torch.cuda.device_count()}')
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(f'  [{i}] {p.name} / {p.total_memory/1024**3:.1f}GB')
else:
    print('!! CUDA 사용 불가. NVIDIA 드라이버/CUDA Toolkit 확인 필요 !!')
"@
