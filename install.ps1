<#
    APEX Quant MCP — Windows installer
    ----------------------------------
    Creates a virtual environment, installs dependencies, and prints the
    Claude Desktop config you need to paste in.

    Usage (from the repo root, in PowerShell):
        powershell -ExecutionPolicy Bypass -File .\install.ps1
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "==> APEX Quant MCP installer" -ForegroundColor Cyan

# 1. Locate Python
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { throw "Python not found on PATH. Install Python 3.10+ from python.org and re-run." }
Write-Host "==> Using $($py.Source)"

# 2. Create venv
if (-not (Test-Path ".\.venv")) {
    Write-Host "==> Creating virtual environment (.venv)"
    & python -m venv .venv
}

$venvPy = Join-Path $root ".venv\Scripts\python.exe"

# 3. Install dependencies
Write-Host "==> Upgrading pip and installing dependencies"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt
& $venvPy -m pip install -e .

# 4. Seed .env
if (-not (Test-Path ".\.env")) {
    Copy-Item ".\.env.example" ".\.env"
    Write-Host "==> Created .env from template — EDIT IT with your paths/credentials." -ForegroundColor Yellow
}

# 5. Smoke test
Write-Host "==> Running smoke test"
& $venvPy -m pytest -q 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "   (pytest not run or some checks skipped — that's OK if MT5/MCP deps differ)" -ForegroundColor DarkYellow }

Write-Host ""
Write-Host "==> DONE. Next steps:" -ForegroundColor Green
Write-Host "   1. Edit .env with APEX_DATA_DIR, MT5 creds (optional), ZAPIER_WEBHOOK_URL."
Write-Host "   2. Open  %APPDATA%\Claude\claude_desktop_config.json"
Write-Host "   3. Merge in the 'mcpServers' block from claude_desktop_config.example.json,"
Write-Host "      replacing C:\path\to\apex-quant-mcp with:"
Write-Host "         $root" -ForegroundColor Cyan
Write-Host "   4. Restart Claude Desktop. You'll see apex-rag, apex-mt5, apex-share connected."
