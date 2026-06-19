@echo off
REM ===========================================================================
REM start_apex_backend.bat
REM Starts the APEX QUANT FastAPI/uvicorn backend.
REM The backend now SURVIVES this window closing because it is launched
REM detached and windowless via pythonw.exe (no attached console).
REM If the backend is already listening on the port, it will NOT start a
REM second copy.
REM ===========================================================================

REM ---- Configurable values (edit these if paths/port change) ----------------
set "BACKEND_DIR=J:\APEX_AGI_Forex_Trading_Bot\APEX QUANT\scaffold\backend"
set "PYW=J:\APEX_AGI_Forex_Trading_Bot\APEX QUANT\.venv\Scripts\pythonw.exe"
set "PORT=8010"
set "UVICORN_ARGS=-m uvicorn app.main:app --host 127.0.0.1 --port %PORT%"

echo Checking if backend is already running on port %PORT% ...

REM ---- Is anything already LISTENING on the port? ---------------------------
netstat -ano | findstr ":%PORT%" | findstr LISTENING >nul
if %ERRORLEVEL%==0 (
    echo Backend already running on port %PORT%
    exit /b 0
)

REM ---- Launch detached and windowless. ------------------------------------
REM /D sets the working directory so that "app.main" is importable.
REM Empty "" after start is the window title (required when first arg is quoted).
echo Starting backend (detached, windowless) ...
start "" /D "%BACKEND_DIR%" "%PYW%" %UVICORN_ARGS%

REM ---- Give uvicorn a few seconds to bind the port. -------------------------
timeout /t 6 >nul

REM ---- Re-check whether it actually came up. --------------------------------
netstat -ano | findstr ":%PORT%" | findstr LISTENING >nul
if %ERRORLEVEL%==0 (
    echo Backend is ONLINE on port %PORT%.
) else (
    echo Backend is STILL OFFLINE on port %PORT%.
    echo Run status_apex_backend.bat for details, and make sure the MT5
    echo terminal is running.
)

exit /b 0
