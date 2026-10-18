param(
  [ValidateSet('M1', 'M2', 'M3')]
  [string]$Stage = 'M1',
  [switch]$Live
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Failures = [System.Collections.Generic.List[string]]::new()

function Invoke-Check([string]$Name, [scriptblock]$Command) {
  Write-Host ""
  Write-Host "== $Name =="
  try {
    & $Command
    if ($LASTEXITCODE -ne 0) {
      throw "exit code $LASTEXITCODE"
    }
    Write-Host "PASS: $Name"
  } catch {
    Write-Host "FAIL: $Name — $($_.Exception.Message)"
    $Failures.Add($Name)
  }
}

Push-Location $RepoRoot
try {
  if ($Stage -ne 'M1') {
    throw "Stage $Stage 尚未实现；当前只有 M1 桌面脚手架与后端脚手架。"
  }
  if ($Live) {
    throw '真实服务验收尚未接入：需要可用的 DeepSeek/ASR 配置与已核验的本地服务包。'
  }

  if (Test-Path 'services/workbench/tests') {
    Invoke-Check 'backend pytest' {
      & .venv/Scripts/python.exe -m pytest services/workbench/tests -q
    }
  } else {
    Write-Warning 'services/workbench/tests 不存在；跳过后端测试。'
  }

  if (Test-Path 'scripts/verify-backend.ps1') {
    Invoke-Check 'backend verify script' {
      & powershell -NoProfile -File scripts/verify-backend.ps1
    }
  }

  Invoke-Check 'desktop typecheck' {
    npm --prefix apps/desktop run typecheck
  }

  if (-not $env:ELECTRON_MIRROR) {
    $env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
  }
  if (-not $env:ELECTRON_CUSTOM_DIR) {
    $env:ELECTRON_CUSTOM_DIR = '{{ version }}'
  }

  Invoke-Check 'desktop package build' {
    npm --prefix apps/desktop run package
  }

  Invoke-Check 'packaged service bundle' {
    $serviceExe = Join-Path $RepoRoot 'apps/desktop/out/ZhixuWorkbench-win32-x64/resources/workbench-service/workbench-service.exe'
    if (-not (Test-Path $serviceExe)) {
      throw "安装包缺少本地服务：$serviceExe"
    }
  }

  Invoke-Check 'desktop e2e' {
    npm --prefix apps/desktop run test:e2e -- --grep '@shell|@unit'
  }

  if (Test-Path 'contracts/rpc.schema.json') {
    Invoke-Check 'contract types check' {
      npm --prefix apps/desktop run contracts:types:check
    }
  } else {
    Write-Host 'FAIL: contract schema missing (contracts/rpc.schema.json)'
    $Failures.Add('contract schema')
  }

  if ($Failures.Count -gt 0) {
    Write-Host ""
    Write-Host "M1 verification failed: $($Failures -join ', ')"
    exit 1
  }

  Write-Host ""
  Write-Host 'M1 verification passed.'
} finally {
  Pop-Location
}
