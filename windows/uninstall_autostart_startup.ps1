<#
  uninstall_autostart_startup.ps1
  -------------------------------
  Removes the login auto-start shortcut created by install_autostart_startup.ps1.
  Does NOT stop a backend that is currently running (use stop_apex_backend.bat
  for that). No admin needed.
#>

try { chcp 65001 > $null 2>&1; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$LnkName = "APEX_Backend.lnk"

try {
    $lnkPath = Join-Path ([Environment]::GetFolderPath('Startup')) $LnkName
    if (Test-Path -LiteralPath $lnkPath) {
        Remove-Item -LiteralPath $lnkPath -Force
        Write-Host "Removed startup shortcut: $lnkPath" -ForegroundColor Green
    } else {
        Write-Host "No startup shortcut found (nothing to remove)." -ForegroundColor Yellow
    }
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Read-Host "Press Enter to exit"
