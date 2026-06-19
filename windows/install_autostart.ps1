# ===========================================================================
# install_autostart.ps1
#
# Registers (or re-registers) a Windows Scheduled Task named "APEX_Backend"
# that keeps the APEX trading backend (uvicorn on 127.0.0.1:8010) running:
#   - Starts automatically at user logon.
#   - Auto-restarts if it crashes.
#   - Runs DETACHED & windowless via pythonw.exe (no console window).
#
# The task runs ONLY when the user is logged on, because the backend needs
# the user's interactive session (e.g. the running MetaTrader 5 terminal).
#
# Safe to run multiple times (idempotent): an existing task with the same
# name is removed and re-created.
#
# To remove the task later, run: uninstall_autostart.ps1
# ===========================================================================

# --- Make the console UTF-8 so any non-ASCII output renders correctly. ----
try { chcp 65001 > $null 2>&1; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# --- Configuration (edit here if paths/ports ever change). ----------------
$TaskName = "APEX_Backend"
$Exe      = "J:\APEX_AGI_Forex_Trading_Bot\APEX QUANT\.venv\Scripts\pythonw.exe"
$TaskArgs = "-m uvicorn app.main:app --host 127.0.0.1 --port 8010"
# Working directory is CRITICAL: "app.main" only resolves from here.
$WorkDir  = "J:\APEX_AGI_Forex_Trading_Bot\APEX QUANT\scaffold\backend"
$Port     = 8010

try {
    Write-Host "Installing scheduled task '$TaskName' ..." -ForegroundColor Cyan

    # --- Define the action: launch pythonw.exe -m uvicorn ... in $WorkDir.
    $action = New-ScheduledTaskAction -Execute $Exe -Argument $TaskArgs -WorkingDirectory $WorkDir

    # --- Trigger: start at user logon.
    $trigger = New-ScheduledTaskTrigger -AtLogOn

    # --- Settings: survive battery, start when available, and auto-restart
    #     on failure (up to 999 times, 1 minute apart). No execution time
    #     limit so the backend can run indefinitely.
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)

    # --- Principal: current user, interactive, run only when logged on.
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited

    # --- Idempotency: if a task with this name already exists, remove it
    #     first so re-running this script cleanly replaces it.
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Existing task found - removing it before re-creating ..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # --- Register the task.
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Keeps the APEX trading backend (uvicorn :8010) running." | Out-Null

    Write-Host "Scheduled task '$TaskName' registered." -ForegroundColor Green

    # --- Start it immediately so the user doesn't have to log off/on.
    Write-Host "Starting the backend now ..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $TaskName

    # --- Give uvicorn a few seconds to come up, then verify the port.
    Start-Sleep -Seconds 6
    Write-Host "Verifying that port $Port is listening ..." -ForegroundColor Cyan
    $check = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue

    Write-Host ""
    if ($check -and $check.TcpTestSucceeded) {
        Write-Host "SUCCESS: APEX backend is running and listening on 127.0.0.1:$Port." -ForegroundColor Green
        Write-Host "It will now auto-start at every logon and auto-restart if it crashes."
    } else {
        Write-Host "Task installed, but port $Port is NOT listening yet." -ForegroundColor Yellow
        Write-Host "It may still be starting up. Check again in a moment, or review:"
        Write-Host "  - Backend status: status_apex_backend.bat"
        Write-Host "  - Task Scheduler (taskschd.msc) -> Task Scheduler Library -> '$TaskName'"
        Write-Host "Also confirm these paths exist on this machine:"
        Write-Host "    Exe    : $Exe"
        Write-Host "    WorkDir: $WorkDir"
    }

    Write-Host ""
    Write-Host "To check it later   : open Task Scheduler (taskschd.msc) and look for '$TaskName',"
    Write-Host "                      or run status_apex_backend.bat."
    Write-Host "To remove autostart : run uninstall_autostart.ps1"
}
catch {
    Write-Host ""
    Write-Host "ERROR: Failed to install the scheduled task." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Tips:"
    Write-Host "  - Right-click this file and choose 'Run with PowerShell'."
    Write-Host "  - If you see an execution-policy error, open PowerShell and run:"
    Write-Host "        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"
    Write-Host "    then run this script again."
    Write-Host "  - Make sure the J: drive and the paths above are available."
}

Read-Host "Press Enter to exit"
