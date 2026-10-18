param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv/Scripts/python.exe'

Push-Location $RepoRoot
try {
  if (-not (Test-Path -LiteralPath $Python)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
      throw 'Python launcher missing. Install CPython 3.14 and retry.'
    }
    & py -3.14 -m venv (Join-Path $RepoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create project Python 3.14 environment.' }
  }

  & $Python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)'
  if ($LASTEXITCODE -ne 0) { throw 'The existing .venv requires Python 3.14.' }

  & $Python -m pip install --require-hashes -r 'services/workbench/requirements.lock'
  if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
  & $Python -m pip install --no-deps --no-build-isolation -e 'services/workbench'
  if ($LASTEXITCODE -ne 0) { throw 'Editable backend installation failed.' }
  & $Python -m pip check
  if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies are inconsistent.' }

  & $Python 'scripts/export-contracts.py'
  if ($LASTEXITCODE -ne 0) { throw 'Contract schema export failed.' }
  Write-Host 'Backend bootstrap complete (project .venv only).'
} finally {
  Pop-Location
}
