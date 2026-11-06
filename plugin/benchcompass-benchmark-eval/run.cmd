@echo off
rem ============================================================
rem LLMFit Benchmark Eval - Windows cift tikla baslatici (Sprint 27 C2)
rem Ollama calisiyor olmali (port 11434).
rem Kullanim: dosyaya cift tikla -> pipeline calisir, raporlar uretilir.
rem ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [HATA] python PATH'te yok. Python 3.11+ kurun ve tekrar deneyin.
  echo.
  pause
  exit /b 1
)

echo.
echo  LLMFit Benchmark Eval - pipeline baslatiliyor...
echo  Ollama calisiyor mu kontrol edin (port 11434).
echo  Cikmak icin herhangi bir tusa basin.
echo.
python run.py --pipeline
set EXIT_CODE=%ERRORLEVEL%

echo.
if "%EXIT_CODE%"=="0" (
  echo  [OK] Pipeline tamamlandi. Rapor: reports\index.html
) else (
  echo  [HATA] Pipeline basarisiz (exit code %EXIT_CODE%).
)
echo.
pause
exit /b %EXIT_CODE%
