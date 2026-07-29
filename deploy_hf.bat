@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy_hf_backend.ps1" %*
exit /b %ERRORLEVEL%
