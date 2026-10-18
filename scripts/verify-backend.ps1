param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
  throw 'Project .venv missing. Run scripts/bootstrap-backend.ps1 first.'
}

Push-Location $RepoRoot
try {
  & $Python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)'
  if ($LASTEXITCODE -ne 0) { throw 'Backend verification requires Python 3.14.' }
  & $Python -m pip check
  if ($LASTEXITCODE -ne 0) { throw 'Backend dependency check failed.' }
  & $Python -m pytest services/workbench/tests -q
  if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
  & $Python -m compileall -q services/workbench/src scripts/export-contracts.py
  if ($LASTEXITCODE -ne 0) { throw 'Backend compile check failed.' }
  & $Python scripts/export-contracts.py --check
  if ($LASTEXITCODE -ne 0) { throw 'Backend contract schema drifted.' }
  Write-Host 'Backend verification passed. Full M1 acceptance is separate.'
} finally {
  Pop-Location
}
