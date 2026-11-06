@echo off
cd /d "%~dp0"
title BenchCompass
color 0A

echo ============================================
echo   BENCHCOMPASS
echo   Yerel LLM Benchmark Dashboard
echo ============================================
echo.

:: Bagimliliklari kontrol et
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
  echo [KURULUM] Bagimliliklar eksik, yukleniyor...
  pip install -r requirements.txt -q
)
echo [OK] Bagimliliklar tamam

:: Eski sunuculari temizle (port 8788 ve 8790)
echo [TEMIZLIK] Eski servisler temizleniyor...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8788 " ^| findstr "LISTEN"') do (
  taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8790 " ^| findstr "LISTEN"') do (
  taskkill /f /pid %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo [OK] Portlar temiz

echo.
echo [BASLATILIYOR] Servisler ayaga kaldiriliyor...
echo.

:: 1. Dashboard API (port 8788)
echo   [1/3] Dashboard API baslatiliyor (port 8788)...
start "BenchCompass-Dashboard" python -m uvicorn api.main:app --host 0.0.0.0 --port 8788
timeout /t 3 /nobreak >nul

:: 2. Collector API (port 8790)
echo   [2/3] Collector API baslatiliyor (port 8790)...
start "BenchCompass-Collector" python -m uvicorn api.collector_api:app --host 0.0.0.0 --port 8790
timeout /t 2 /nobreak >nul

:: 3. Tarayiciyi ac
echo   [3/3] Dashboard aciliyor...
timeout /t 2 /nobreak >nul
start "" http://localhost:8788

echo.
echo ============================================
echo   ADRESLER
echo   Dashboard : http://localhost:8788
echo   Collector  : http://localhost:8790
echo ============================================
echo.
echo  Servisler ayri pencerelerde calisiyor.
echo  Kapatmak icin servis pencerelerini kapatmaniz yeterli.
echo.
pause
