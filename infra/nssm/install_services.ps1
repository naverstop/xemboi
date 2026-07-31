#requires -RunAsAdministrator
<#
.SYNOPSIS
  NSSM 으로 Saju Agent 운영 서비스 4종 등록:
   - SajuBackend     (uvicorn :8000)
   - SajuCaddy       (Caddy :8080)
   - SajuCloudflared (cloudflared tunnel)
   - SajuFrontend    (Vite preview :5173, dist 빌드 필수)

.PREREQ
  - NSSM 설치 (winget install --id NSSM.NSSM 또는 nssm.cc 에서 다운로드 → PATH)
  - Caddy 설치 (C:\caddy\caddy.exe)
  - cloudflared 설치 (winget install --id Cloudflare.cloudflared)
  - 프론트 빌드 완료 (C:\sajufe\dist 존재)
  - 백엔드 .venv 존재 (E:\3. 개인\## 마누라\Saju_Agent\.venv)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install_services.ps1
  powershell -ExecutionPolicy Bypass -File .\install_services.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$Root      = (Resolve-Path "$PSScriptRoot\..\..").Path
$Venv      = Join-Path $Root '.venv\Scripts\python.exe'
$Logs      = Join-Path $Root 'logs'
$CaddyExe  = 'C:\caddy\caddy.exe'
$CaddyCfg  = Join-Path $Root 'infra\caddy\Caddyfile'
$CfExe     = "$env:ProgramFiles\cloudflared\cloudflared.exe"
$CfCfg     = Join-Path $Root 'infra\cloudflared\config.yml'
$NodePath  = "$env:LOCALAPPDATA\nodejs"
$FePath    = 'C:\sajufe'

if (-not (Test-Path $Logs)) { New-Item -ItemType Directory -Path $Logs | Out-Null }

function Test-Nssm {
    if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
        throw "nssm.exe 가 PATH 에 없습니다. 'winget install --id NSSM.NSSM' 후 새 셸에서 다시 실행하세요."
    }
}

function Install-Service($Name, $Exe, $Args, $WorkDir, $LogBase) {
    Write-Host "[install] $Name" -ForegroundColor Cyan
    & nssm install $Name $Exe $Args | Out-Null
    & nssm set $Name AppDirectory $WorkDir | Out-Null
    & nssm set $Name AppStdout "$Logs\$LogBase.out.log" | Out-Null
    & nssm set $Name AppStderr "$Logs\$LogBase.err.log" | Out-Null
    & nssm set $Name AppRotateFiles 1 | Out-Null
    & nssm set $Name AppRotateBytes 52428800 | Out-Null
    & nssm set $Name Start SERVICE_AUTO_START | Out-Null
}

function Uninstall-Service($Name) {
    Write-Host "[remove] $Name" -ForegroundColor Yellow
    & nssm stop $Name confirm 2>$null | Out-Null
    & nssm remove $Name confirm 2>$null | Out-Null
}

$services = @('SajuBackend', 'SajuCaddy', 'SajuCloudflared', 'SajuFrontend')

if ($Uninstall) {
    Test-Nssm
    $services | ForEach-Object { Uninstall-Service $_ }
    Write-Host "Done." -ForegroundColor Green
    return
}

Test-Nssm

# 사전 점검
@(
    @{ p = $Venv;     n = 'Python venv' },
    @{ p = $CaddyExe; n = 'Caddy' },
    @{ p = $CfExe;    n = 'cloudflared' },
    @{ p = $NodePath; n = 'Node.js' }
) | ForEach-Object {
    if (-not (Test-Path $_.p)) { Write-Warning ("[누락] {0}: {1}" -f $_.n, $_.p) }
}

# 1) Backend (uvicorn)
Install-Service `
    -Name 'SajuBackend' `
    -Exe  $Venv `
    -Args '-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level info' `
    -WorkDir $Root `
    -LogBase 'backend'

# 2) Caddy
Install-Service `
    -Name 'SajuCaddy' `
    -Exe  $CaddyExe `
    -Args ("run --config `"{0}`"" -f $CaddyCfg) `
    -WorkDir (Split-Path $CaddyCfg) `
    -LogBase 'caddy'

# 3) Cloudflared tunnel
Install-Service `
    -Name 'SajuCloudflared' `
    -Exe  $CfExe `
    -Args ("tunnel --config `"{0}`" run" -f $CfCfg) `
    -WorkDir (Split-Path $CfCfg) `
    -LogBase 'cloudflared'

# 4) Frontend (Vite preview)
if (Test-Path "$FePath\dist") {
    Install-Service `
        -Name 'SajuFrontend' `
        -Exe  "$NodePath\node.exe" `
        -Args ("`"{0}\npm-cli.js`" --prefix `"{1}`" exec -- vite preview --port 5173 --host 127.0.0.1" -f "$NodePath\node_modules\npm\bin", $FePath) `
        -WorkDir $FePath `
        -LogBase 'frontend'
} else {
    Write-Warning "C:\sajufe\dist 가 없어 SajuFrontend 등록을 건너뜁니다. 'cd C:\sajufe; npx vite build' 후 다시 실행하세요."
}

Write-Host ""
Write-Host "=== 등록 완료 ===" -ForegroundColor Green
Write-Host "기동: Start-Service SajuBackend, SajuCaddy, SajuCloudflared, SajuFrontend"
Write-Host "정지: Stop-Service  SajuBackend, SajuCaddy, SajuCloudflared, SajuFrontend"
Write-Host "상태: Get-Service Saju*"
Write-Host "해제: install_services.ps1 -Uninstall"
