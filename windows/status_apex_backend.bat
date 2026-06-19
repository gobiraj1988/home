@echo off
REM ===========================================================================
REM status_apex_backend.bat
REM Reports whether the APEX QUANT backend is up. Because the backend runs
REM detached/windowless via pythonw.exe, you cannot tell by looking for a
REM window; we check the listening port instead and show the owning process.
REM ===========================================================================

set "PORT=8010"

echo Checking backend status on port %PORT% ...

powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue; if($c){ $p=Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue; Write-Host ('ONLINE (pid {0}) {1} {2}' -f $c.OwningProcess, $p.ProcessName, $p.Path) } else { Write-Host 'OFFLINE' }; Test-NetConnection 127.0.0.1 -Port 8010 | Out-Host"

exit /b 0
