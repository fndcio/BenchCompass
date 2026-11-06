$ErrorActionPreference = 'Stop'
try {
  $base = Split-Path -Parent $MyInvocation.MyCommand.Path
  Set-Location $base
  Write-Host "Dashboard server baslatiliyor: http://localhost:8788" -ForegroundColor Cyan

  # Port 8788'deki eski process'i temizle
  $existing = netstat -ano | Select-String ":8788 " | Select-String "LISTENING"
  if ($existing) {
    $oldPid = ($existing -split '\s+')[-1]
    Write-Host "Eski process bulundu (PID: $oldPid), sonlandiriliyor..." -ForegroundColor Yellow
    taskkill /F /PID $oldPid 2>$null
    Start-Sleep -Seconds 1
  }

  # Bagimliliklari kontrol et
  $needInstall = $false
  try { python -c "import fastapi, uvicorn, pydantic" 2>$null }
  catch { $needInstall = $true }
  if ($LASTEXITCODE -ne 0) { $needInstall = $true }
  if ($needInstall) {
    Write-Host "Bagimliliklar eksik, requirements.txt kuruluyor..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt --quiet
  }

  python -m uvicorn api.main:app --host 0.0.0.0 --port 8788 --reload
}
catch {
  Write-Host "HATA: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
  Write-Host "Kapatmak icin Enter'a bas..." -ForegroundColor Yellow
  Read-Host
}
