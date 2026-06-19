@echo off
REM ===========================================================================
REM START_APEX_ALL.bat
REM One-click launcher: starts the APEX QUANT backend (detached/windowless via
REM pythonw.exe, so it survives this window closing), then opens the trading
REM dashboard in the default browser.
REM ===========================================================================

echo ==========================================
echo   APEX QUANT - One-Click Startup
echo ==========================================
echo.

echo [1/2] Starting backend ...
call "%~dp0start_apex_backend.bat"

echo.
echo Waiting a moment before opening the dashboard ...
timeout /t 3 >nul

echo [2/2] Opening dashboard in your default browser ...
start "" "J:\My_Trader\dashboard\nexus_terminal.html"

echo.
echo Done. The backend keeps running even if you close this window.
echo Use status_apex_backend.bat to check it, or stop_apex_backend.bat to stop it.

exit /b 0
