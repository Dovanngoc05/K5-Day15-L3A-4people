<#
.SYNOPSIS
    Khoi chay nhanh Backend (FastAPI) va Frontend (Vite) tren may Windows local.
.EXAMPLE
    .\scripts\dev.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".local_data\app.db")) {
    Write-Host "[1/3] Khoi tao co so du lieu SQLite bang Alembic..." -ForegroundColor Cyan
    python -m alembic upgrade head
}

$env:PYTHONIOENCODING = "utf-8"
Write-Host "[2/3] Dang bat FastAPI Backend tai http://127.0.0.1:8000 (OpenAPI: /docs)..." -ForegroundColor Green
$backendProc = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" -WorkingDirectory $Root -PassThru

try {
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "Dang cai dat npm dependencies cho frontend..." -ForegroundColor Yellow
        Push-Location "frontend"
        npm install
        Pop-Location
    }
    Write-Host "[3/3] Dang bat Vite Frontend tai http://localhost:5173 ..." -ForegroundColor Green
    Write-Host "Nhan Ctrl+C de dung ca Frontend va Backend." -ForegroundColor Gray
    Push-Location "frontend"
    npm run dev
}
finally {
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Da dung Backend." -ForegroundColor Yellow
    }
}
