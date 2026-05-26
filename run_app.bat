@echo off
title Richa Global - Employee Task & Attendance Management System
color 0B
echo ======================================================================
echo          RICHA GLOBAL - TASK & ATTENDANCE MANAGEMENT SYSTEM          
echo ======================================================================
echo.
echo [1] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not added to your system PATH.
    echo Please install Python from python.org and check "Add Python to PATH".
    pause
    exit /b
)

echo [2] Installing / Checking required libraries...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo WARNING: Dependency installation encountered some warnings/errors.
    echo We will still attempt to run the server.
    echo.
)

echo [3] Opening Dashboard in your browser...
:: Delay opening the browser slightly to let the Flask server start up
start http://127.0.0.1:5000

echo [4] Starting Flask + SocketIO Server...
echo ======================================================================
echo Server is running! Keep this window open while using the app.
echo To stop the server, close this window or press Ctrl+C.
echo ======================================================================
echo.

python run.py
pause
