# ===========================================================================
# uninstall_autostart.ps1
#
# Stops and removes the "APEX_Backend" scheduled task created by
# install_autostart.ps1, so the backend no longer auto-starts at logon.
#
# NOTE: This does NOT stop a currently-running backend process. The backend
# runs detached/windowless via pythonw.exe, so to stop the live process use
# stop_apex_backend.bat.
#
# Safe to run multiple times (idempotent).
# ===========================================================================

# --- Make the console UTF-8 so any non-ASCII output renders correctly. ----
try { chcp 65001 > $null 2>&1; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$TaskName = "APEX_Backend"

try {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        # Stop the task instance if running (ignore errors if it isn't).
        try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}

        # Remove the task definition.
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false

        Write-Host "Removed: scheduled task '$TaskName' has been deleted." -ForegroundColor Green
        Write-Host "Note: this did NOT stop a running backend." -ForegroundColor Yellow
        Write-Host "      To stop the live backend process, run stop_apex_backend.bat."
    } else {
        Write-Host "Was not installed: no scheduled task named '$TaskName' was found." -ForegroundColor Yellow
    }
}
catch {
    Write-Host "ERROR: Failed to remove the scheduled task." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Read-Host "Press Enter to exit"
