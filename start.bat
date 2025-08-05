@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ================================================
echo              Screen Share Service
echo ================================================
echo.
echo Starting server...
echo.

REM Start server in background
start /B python main.py

REM Wait for server to start
echo Waiting for server startup...
timeout /t 5 /nobreak >nul

REM Get local IP address
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    set "ip=%%i"
    set "ip=!ip: =!"
    goto :gotip
)
:gotip

REM Open browser with local IP
echo Opening browser...
echo Accessing: https://%ip%:443
start https://%ip%:443

echo.
echo Server is running. Press any key to stop...
pause >nul

REM Kill Python processes
taskkill /f /im python.exe >nul 2>&1
echo Server stopped.
