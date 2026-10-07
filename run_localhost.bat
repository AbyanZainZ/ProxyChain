@echo off
title ProxyChain Gateway - Localhost Launcher
color 0B
cls

echo ==============================================================================
echo        PROXYCHAIN GATEWAY - LOCALHOST LAUNCHER (CYBER COCKPIT)
echo ==============================================================================
echo.

cd /d "%~dp0"

echo [1/3] Memeriksa instalasi Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak ditemukan di PATH sistem Anda!
    echo Silakan install Python 3.10+ dari https://www.python.org/
    pause
    exit /b 1
)

echo [2/3] Memeriksa dependensi (FastAPI, Uvicorn, httpx, dll)...
python -m pip install -r requirements.txt >nul 2>&1

echo [3/3] Menjalankan ProxyChain Web Dashboard di http://127.0.0.1:8080 ...
echo.
echo ==============================================================================
echo  Web Dashboard  : http://127.0.0.1:8080
echo  Default Auth   : gemini / gemini
echo  Proxy Ports    : 10001+
echo ==============================================================================
echo.
echo Tekan CTRL + C di jendela ini untuk menghentikan server.
echo.

:: Buka browser otomatis setelah 1.5 detik
start "" http://127.0.0.1:8080

:: Jalankan server uvicorn
python -m uvicorn app:app --host 127.0.0.1 --port 8080

pause
