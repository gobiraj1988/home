<#
  install_autostart_startup.ps1   (RECOMMENDED -- no admin needed)
  ----------------------------------------------------------------
  Makes the APEX backend start automatically at every Windows login by
  placing a shortcut in your personal Startup folder. The backend runs
  DETACHED & windowless via pythonw.exe, so it keeps running even after you
  close every window, and comes back on its own after a reboot/login.

  This does NOT require Administrator rights (unlike the Scheduled Task
  version, install_autostart.ps1).

  Usage: right-click this file -> "Run with PowerShell".
  To undo: run uninstall_autostart_startup.ps1 (or delete the shortcut from
           the Startup folder -- run  shell:startup  in the Run box).
#>

try { chcp 65001 > $null 2>&1; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# --- Configuration (edit if paths/port change) ---------------------------
$Pyw     = "J:\APEX_AGI_Forex_Trading_Bot\APEX QUANT\.venv\Scripts\pythonw.exe"
$Args    = "-m uvicorn app.main:app --host 127.0.0.1 --port 8010"
$WorkDir = "J:\APEX_AGI_Forex_Trading_Bot\APEX QUANT\scaffold\backend"
$Port    = 8010
$LnkName = "APEX_Backend.lnk"

try {
    $startup  = [Environment]::GetFolderPath('Startup')
    $lnkPath  = Join-Path $startup $LnkName

    Write-Host "Creating startup shortcut:" -ForegroundColor Cyan
    Write-Host "  $lnkPath"

    # Sanity check the target exists so we fail early with a clear message.
    if (-not (Test-Path -LiteralPath $Pyw)) {
        throw "pythonw.exe not found at: $Pyw  (check the path / J: drive)."
    }
    if (-not (Test-Path -LiteralPath $WorkDir)) {
        throw "Backend folder not found at: $WorkDir"
    }

    $WshShell = New-Object -ComObject WScript.Shell
    $lnk = $WshShell.CreateShortcut($lnkPath)
    $lnk.TargetPath       = $Pyw
    $lnk.Arguments        = $Args
    $lnk.WorkingDirectory = $WorkDir
    $lnk.WindowStyle      = 7   # minimized (pythonw has no window anyway)
    $lnk.Description       = "Starts the APEX trading backend (uvicorn :$Port) at login."
    $lnk.Save()

    Write-Host ""
    Write-Host "SUCCESS: the backend will now auto-start every time you log in." -ForegroundColor Green
    Write-Host "No Administrator rights were needed."
    Write-Host ""
    Write-Host "Start it right now without rebooting? Run START_APEX_ALL.bat, or:"
    Write-Host "  Start-Process -FilePath `"$Pyw`" -ArgumentList `"-m`",`"uvicorn`",`"app.main:app`",`"--host`",`"127.0.0.1`",`"--port`",`"$Port`" -WorkingDirectory `"$WorkDir`""
    Write-Host ""
    Write-Host "To undo: run uninstall_autostart_startup.ps1, or open the Run box"
    Write-Host "         (Win+R), type  shell:startup  and delete '$LnkName'."
}
catch {
    Write-Host ""
    Write-Host "ERROR: could not create the startup shortcut." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Read-Host "Press Enter to exit"
