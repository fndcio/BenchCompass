$ErrorActionPreference = 'Stop'
try {
  $base = Split-Path -Parent $MyInvocation.MyCommand.Path
  Set-Location $base
  Write-Host "Collector bir kez çalıştırılıyor..." -ForegroundColor Cyan
  python .\benchmark_collector.py
}
catch {
  Write-Host "HATA: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
  Write-Host "Kapatmak için Enter'a bas..." -ForegroundColor Yellow
  Read-Host
}
