$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11+ is required. Install Python and reopen PowerShell."
}

python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
if ($LASTEXITCODE -ne 0) { throw "Unsupported Python version." }

python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Could not create virtual environment." }

$Python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

& $Python -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "MITRA development dependencies failed to install." }

& $Python -m pytest
if ($LASTEXITCODE -ne 0) { throw "MITRA test suite failed." }

& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff found code quality issues." }

Write-Host "MITRA checks completed successfully."
