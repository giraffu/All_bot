@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0start_worker_remote_01.ps1" %*
if errorlevel 1 pause
