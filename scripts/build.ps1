param(
  [ValidateSet('M1', 'M2', 'M3')]
  [string]$Stage = 'M1',
  [switch]$Make,
  [switch]$AllowShellOnly
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$RepoRoot = Split-Path -Parent $PSScriptRoot

if ($Stage -ne 'M1') {
  throw "Stage $Stage 尚未实现；当前只有 M1 桌面脚手架。"
}

if (-not $env:ELECTRON_MIRROR) {
  $env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
}
if (-not $env:ELECTRON_CUSTOM_DIR) {
  $env:ELECTRON_CUSTOM_DIR = '{{ version }}'
}

Push-Location $RepoRoot
try {
  $pyinstaller = Join-Path $RepoRoot '.venv/Scripts/pyinstaller.exe'
  if (Test-Path $pyinstaller) {
    Push-Location 'services/workbench'
    try {
      & $pyinstaller `
        --noconfirm --clean --onedir `
        --name workbench-service `
        --paths src `
        --distpath dist `
        --workpath build `
        --specpath build `
        src/workbench/__main__.py
    } finally {
      Pop-Location
    }
  } else {
    Write-Warning '未找到 PyInstaller；安装包不会包含本地服务，仅验证桌面壳。'
  }

  npm --prefix apps/desktop run package
  if ($Make) {
    npm --prefix apps/desktop run make
  }

  $serviceExe = Join-Path $RepoRoot 'apps/desktop/out/ZhixuWorkbench-win32-x64/resources/workbench-service/workbench-service.exe'
  if (-not (Test-Path $serviceExe)) {
    if (-not $AllowShellOnly) {
      throw "安装包缺少本地服务：$serviceExe。使用 -AllowShellOnly 仅构建桌面壳。"
    }
    Write-Warning '安装包未包含本地服务；这是显式允许的 shell-only 构建。'
  }

  $output = Join-Path $RepoRoot 'apps/desktop/out'
  Write-Host "build complete: $output"
} finally {
  Pop-Location
}
