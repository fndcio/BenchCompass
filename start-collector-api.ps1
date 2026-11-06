$ErrorActionPreference = 'Stop'
try {
  $base = Split-Path -Parent $MyInvocation.MyCommand.Path
  Set-Location $base
  Write-Host "Collector API baslatiliyor: http://localhost:8790" -ForegroundColor Cyan

  # Sprint 3: FastAPI'ye gecis.
  $needInstall = $false
  try { python -c "import fastapi, uvicorn, pydantic" 2>$null }
  catch { $needInstall = $true }
  if ($LASTEXITCODE -ne 0) { $needInstall = $true }
  if ($needInstall) {
    Write-Host "Bagimliliklar eksik, requirements.txt kuruluyor..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt --quiet
  }

  python -m uvicorn api.collector_api:app --host 0.0.0.0 --port 8790
}
catch {
  Write-Host "HATA: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
  Write-Host "Kapatmak icin Enter'a bas..." -ForegroundColor Yellow
  Read-Host
}
