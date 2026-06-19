@echo off
REM ===========================================================================
REM stop_apex_backend.bat
REM Stops the APEX QUANT backend by killing whatever process is listening on
REM the backend port. Because the backend runs detached/windowless via
REM pythonw.exe, there is no console window to close, so we stop it by port.
REM ===========================================================================

set "PORT=8010"

echo Stopping backend on port %PORT% ...

powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue; if($c){ Stop-Process -Id $c.OwningProcess -Force; 'Backend stopped.' } else { 'Backend was not running.' }"

exit /b 0
