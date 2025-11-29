@echo off
REM Test script specifically for base framework that copies the senders package
REM Usage: test_base_framework.bat

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "CONTAINER_NAME=ecs152a-simulator"
set "SENDER_FILE=%SCRIPT_DIR%..\senders\base_sender_test.py"

echo ==========================================
echo Base Framework Test
echo ==========================================
echo [INFO] Copying senders package into container...
docker cp "%SCRIPT_DIR%..\senders" %CONTAINER_NAME%:/app/senders
if errorlevel 1 (
    echo [ERROR] Failed to copy senders package
    exit /b 1
)
echo [SUCCESS] Senders package copied to /app/senders

echo.
echo [INFO] Running test with test_sender.bat...
echo [INFO] Note: Python should find /app/senders automatically
echo.
call "%SCRIPT_DIR%test_sender.bat" "%SENDER_FILE%"

