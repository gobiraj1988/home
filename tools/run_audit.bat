@echo off
REM ============================================================
REM  run_audit.bat -- double-click இதை, audit report வரும்.
REM  இது எதையும் delete பண்ணாது (READ-ONLY).
REM ============================================================
cd /d "%~dp0"
echo Starting APEX Quant J: drive audit (read-only)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0audit_J_drive.ps1"
echo.
pause
