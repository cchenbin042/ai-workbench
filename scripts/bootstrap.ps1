param(
  [switch]$SkipBackend,
  [switch]$SkipDesktop
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$RepoRoot = Split-Path -Parent $PSScriptRoot
$NodeMajor = 24
$PythonSelector = 'py -3.14'

function Assert-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "缺少命令：$Name"
  }
}

function Set-ElectronMirrorDefault {
  if (-not $env:ELECTRON_MIRROR) {
    $env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
  }
  if (-not $env:ELECTRON_CUSTOM_DIR) {
    $env:ELECTRON_CUSTOM_DIR = '{{ version }}'
  }
}

Push-Location $RepoRoot
try {
  Assert-Command node
  $nodeVersion = (node -v).Trim()
  if (-not $nodeVersion.StartsWith("v$NodeMajor.")) {
    throw "需要 Node.js $NodeMajor LTS，当前为 $nodeVersion"
  }

  if (-not $SkipBackend) {
    if (Test-Path 'scripts/bootstrap-backend.ps1') {
      & powershell -NoProfile -File scripts/bootstrap-backend.ps1
    } else {
      & py -3.14 -c "import sys; print(sys.version)" | Out-Null
      if (-not (Test-Path '.venv/Scripts/python.exe')) {
        & py -3.14 -m venv .venv
      }
      $python = Join-Path $RepoRoot '.venv/Scripts/python.exe'
      & $python -m pip install --upgrade pip | Out-Null
      if (Test-Path 'services/workbench/requirements.lock') {
        & $python -m pip install --require-hashes -r services/workbench/requirements.lock
      } elseif (Test-Path 'services/workbench/pyproject.toml') {
        & $python -m pip install -e 'services/workbench[dev]'
      }
      if (Test-Path 'services/workbench/pyproject.toml') {
        & $python -m pip install --no-deps -e services/workbench
      }
    }
  }

  if (-not $SkipDesktop) {
    Push-Location 'apps/desktop'
    try {
      if (Test-Path 'package-lock.json') {
        npm ci
      } else {
        npm install
      }
      Set-ElectronMirrorDefault
      if (-not (Test-Path 'node_modules/electron/dist/electron.exe')) {
        node node_modules/electron/install.js
      }
    } finally {
      Pop-Location
    }

    if (Test-Path 'contracts/rpc.schema.json') {
      Push-Location 'apps/desktop'
      try {
        npm run contracts:types
      } finally {
        Pop-Location
      }
    } else {
      Write-Warning 'contracts/rpc.schema.json 尚未生成；跳过 TypeScript 契约生成。'
    }
  }

  $pythonVersion = '未创建'
  if (Test-Path '.venv/Scripts/python.exe') {
    $pythonVersion = (& .venv/Scripts/python.exe --version).Trim()
  }
  Write-Host "bootstrap complete: node=$nodeVersion python=$pythonVersion"
} finally {
  Pop-Location
}
