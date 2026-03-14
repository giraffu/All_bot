@echo off
echo ===================================================
echo       Starting TeleBot Dashboard System
echo ===================================================

echo [1/2] Starting Backend Server (Port 8043)...
start "Dashboard Backend" cmd /k "cd dashboard\backend && ..\..\.venv\Scripts\python.exe main.py"

echo [2/2] Starting Frontend Server...
start "Dashboard Frontend" cmd /k "cd dashboard\frontend && npm install && npm run dev -- --host"

echo.
echo Success! 
echo Frontend will be available at: http://localhost:5173
echo.
echo [LAN ACCESS]
echo To access from other computers in your network:
echo 1. Find your IP address (run 'ipconfig' in cmd)
echo 2. Open: http://YOUR_IP_ADDRESS:5173
echo.
echo Backend API is running at: http://0.0.0.0:8043
echo.
pause
