# One-command local run on Windows (PowerShell): .\start.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location "$Root\backend"
if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtualenv (backend\.venv)..."
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { python -m venv .venv }
}
$Py = "$Root\backend\.venv\Scripts\python.exe"
& $Py -c "import fastapi, rapidocr_onnxruntime" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing backend dependencies..."
    & $Py -m pip install -q --upgrade pip
    # truststore uses the Windows certificate store (works behind antivirus / corporate HTTPS inspection)
    & $Py -m pip install -q --use-feature=truststore -r requirements.txt
}
if (-not (Test-Path "storage\dataset\manifest.json")) { & $Py "..\scripts\generate_dataset.py" | Out-Null }

Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) { Write-Host "Installing frontend dependencies..."; npm ci --no-audit --no-fund }

$api = Start-Process -FilePath $Py -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75" `
    -WorkingDirectory "$Root\backend" -PassThru -NoNewWindow
try {
    Write-Host ""
    Write-Host "  Web app   http://localhost:3000   (demo login: merchant@pramaan.local / shopkeeper123)"
    Write-Host "  API docs  http://localhost:8000/docs"
    Write-Host ""
    npm run dev
}
finally {
    Write-Host "Stopping Pramaan..."
    Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
