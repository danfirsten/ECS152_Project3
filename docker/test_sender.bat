@echo off
REM Unified test script for students to test their sender implementation (Windows)
REM Usage: test_sender.bat <your_sender.py> [payload_file]

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "CONTAINER_NAME=ecs152a-simulator"

if "%~1"=="" (
    echo [ERROR] No sender file specified
    echo Usage: test_sender.bat ^<your_sender.py^> [payload_file]
    echo Example: test_sender.bat my_tcp_tahoe.py file.zip
    exit /b 1
)

set "SENDER_FILE=%~1"
if not exist "%SENDER_FILE%" (
    echo [ERROR] Sender file '%SENDER_FILE%' not found
    exit /b 1
)

set "PAYLOAD_ARG=%~2"
if "%PAYLOAD_ARG%"=="" set "PAYLOAD_ARG=file.zip"

if not defined NUM_RUNS set "NUM_RUNS=10"
if not defined RECEIVER_PORT set "RECEIVER_PORT=5001"

call :resolve_payload "%PAYLOAD_ARG%" PAYLOAD_SOURCE
if errorlevel 1 (
    echo [ERROR] Could not locate payload file '%PAYLOAD_ARG%'.
    echo         Looked relative to current dir, %SCRIPT_DIR% and %SCRIPT_DIR%hdd.
    exit /b 1
)

for %%I in ("%PAYLOAD_SOURCE%") do set "PAYLOAD_BASENAME=%%~nxi"
call :derive_received "%PAYLOAD_BASENAME%" RECEIVED_BASENAME

set "CONTAINER_PAYLOAD_FILE=/hdd/%PAYLOAD_BASENAME%"
set "CONTAINER_OUTPUT_FILE=/hdd/%RECEIVED_BASENAME%"

echo ==========================================
echo ECS 152A - Testing Your Sender Implementation
echo ==========================================
echo [INFO] Sender file : %SENDER_FILE%
echo [INFO] Payload file: %PAYLOAD_SOURCE% ^(copied as %CONTAINER_PAYLOAD_FILE%^)
echo [INFO] Receiver port (inside container): %RECEIVER_PORT%

echo.
echo ==========================================
echo Step 1/4: Pre-flight Checks
echo ==========================================
echo [INFO] Checking Docker installation...
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not installed or not in PATH
    echo Please install Docker Desktop. See SETUP.md for instructions.
    exit /b 1
)
echo [SUCCESS] Docker is installed

echo [INFO] Checking if Docker daemon is running...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker daemon is not running
    echo Please start Docker Desktop from the Start menu
    exit /b 1
)
echo [SUCCESS] Docker daemon is running

echo [INFO] Checking if simulator container exists...
echo [DEBUG] Looking for container name: %CONTAINER_NAME%
echo [DEBUG] All containers:
docker ps -a --format "{{.Names}}" 
echo [DEBUG] Running containers:
docker ps --format "{{.Names}}"
docker ps -a --format "{{.Names}}" | findstr /x "%CONTAINER_NAME%" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Simulator container not found
    echo [INFO] Starting simulator for the first time...
    call "%SCRIPT_DIR%start_sim.bat"
    timeout /t 5 /nobreak >nul
    echo [DEBUG] After starting, checking container status...
    docker ps -a --filter "name=%CONTAINER_NAME%" --format "{{.Names}} {{.Status}}"
) else (
    echo [DEBUG] Container found, checking if running...
    docker ps --format "{{.Names}}" | findstr /x "%CONTAINER_NAME%" >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Simulator container exists but is not running
        echo [DEBUG] Container status:
        docker ps -a --filter "name=%CONTAINER_NAME%" --format "{{.Names}} {{.Status}}"
        echo [INFO] Starting simulator...
        docker start %CONTAINER_NAME% >nul 2>&1
        timeout /t 3 /nobreak >nul
        echo [DEBUG] After start command, container status:
        docker ps --filter "name=%CONTAINER_NAME%" --format "{{.Names}} {{.Status}}"
    ) else (
        echo [INFO] Simulator container is already running
        echo [DEBUG] Container details:
        docker ps --filter "name=%CONTAINER_NAME%" --format "{{.Names}} {{.Status}} {{.ID}}"
    )
)

echo.
echo ==========================================
echo Step 2/4: Preparing Test Environment
echo ==========================================
echo [INFO] Copying your sender file into container...
echo [DEBUG] Container name: %CONTAINER_NAME%
echo [DEBUG] Sender file path: %SENDER_FILE%
echo [DEBUG] Verifying container is running before copy...
docker ps --filter "name=%CONTAINER_NAME%" --format "{{.Names}} {{.Status}}"
echo [DEBUG] Executing: docker cp "%SENDER_FILE%" %CONTAINER_NAME%:/app/sender.py
docker cp "%SENDER_FILE%" %CONTAINER_NAME%:/app/sender.py
set "COPY_EXIT_CODE=%errorlevel%"
echo [DEBUG] Copy command exit code: %COPY_EXIT_CODE%
if errorlevel 1 (
    echo [ERROR] Failed to copy sender file into container
    echo [DEBUG] Checking if container still exists...
    docker ps -a --filter "name=%CONTAINER_NAME%" --format "{{.Names}} {{.Status}}"
    echo [DEBUG] Attempting to verify container accessibility...
    docker exec %CONTAINER_NAME% echo "Container is accessible" 2>&1
    exit /b 1
)
echo [SUCCESS] Sender file copied

echo [INFO] Copying senders package into container...
echo [DEBUG] Senders folder path: %SCRIPT_DIR%..\senders
echo [DEBUG] Executing: docker cp "%SCRIPT_DIR%..\senders" %CONTAINER_NAME%:/app/senders
docker cp "%SCRIPT_DIR%..\senders" %CONTAINER_NAME%:/app/senders
set "SENDERS_COPY_EXIT=%errorlevel%"
echo [DEBUG] Senders copy exit code: %SENDERS_COPY_EXIT%
if errorlevel 1 (
    echo [ERROR] Failed to copy senders package into container
    exit /b 1
)
echo [SUCCESS] Senders package copied to /app/senders


echo [INFO] Copying payload into container...
echo [DEBUG] Payload source: %PAYLOAD_SOURCE%
echo [DEBUG] Container destination: %CONTAINER_PAYLOAD_FILE%
echo [DEBUG] Executing: docker cp "%PAYLOAD_SOURCE%" %CONTAINER_NAME%:%CONTAINER_PAYLOAD_FILE%
docker cp "%PAYLOAD_SOURCE%" %CONTAINER_NAME%:%CONTAINER_PAYLOAD_FILE%
set "PAYLOAD_COPY_EXIT=%errorlevel%"
echo [DEBUG] Payload copy exit code: %PAYLOAD_COPY_EXIT%
if errorlevel 1 (
    echo [ERROR] Failed to copy payload file into container
    exit /b 1
)
echo [SUCCESS] Payload ready

echo.
echo ==========================================
echo Step 3/4: Starting Receiver
echo ==========================================
echo [INFO] Resetting receiver state...
docker exec %CONTAINER_NAME% pkill -f receiver.py >nul 2>&1
docker exec %CONTAINER_NAME% rm -f %CONTAINER_OUTPUT_FILE% >nul 2>&1
docker exec -d %CONTAINER_NAME% env RECEIVER_PORT=%RECEIVER_PORT% TEST_FILE=%CONTAINER_PAYLOAD_FILE% PAYLOAD_FILE=%CONTAINER_PAYLOAD_FILE% RECEIVER_OUTPUT_FILE=%CONTAINER_OUTPUT_FILE% python3 /app/receiver.py >nul 2>&1
timeout /t 2 /nobreak >nul
echo [SUCCESS] Receiver is running inside the container

echo.
echo ==========================================
echo Step 4/4: Running Your Sender
echo ==========================================
echo [INFO] Executing your sender implementation...
echo.

docker exec %CONTAINER_NAME% env RECEIVER_PORT=%RECEIVER_PORT% TEST_FILE=%CONTAINER_PAYLOAD_FILE% PAYLOAD_FILE=%CONTAINER_PAYLOAD_FILE% python3 /app/sender.py 2>&1
set "SENDER_EXIT_CODE=%errorlevel%"
echo.

if not "%SENDER_EXIT_CODE%"=="0" (
    echo [ERROR] Sender exited with error code %SENDER_EXIT_CODE%
    echo [WARNING] Check the output above for error messages
    exit /b 1
)

echo ==========================================
echo Performance Metrics
echo ==========================================
echo [INFO] Check the output above for metrics (CSV format):
echo   throughput,delay,jitter,score
echo.
echo [SUCCESS] Test completed successfully!
echo.

endlocal
exit /b 0

:resolve_payload
set "CANDIDATE=%~1"
set "RESULT_VAR=%~2"

if exist "%CANDIDATE%" (
    for %%F in ("%CANDIDATE%") do (
        set "%RESULT_VAR%=%%~fF"
    )
    exit /b 0
)

set "FIRST_CHAR=%CANDIDATE:~0,1%"
set "IS_ABSOLUTE=0"
if "%FIRST_CHAR%"=="/" set "IS_ABSOLUTE=1"
if "%FIRST_CHAR%"=="\" set "IS_ABSOLUTE=1"
if not "%CANDIDATE:~1,1%"=="" if "%CANDIDATE:~1,1%"==":" set "IS_ABSOLUTE=1"

if "%IS_ABSOLUTE%"=="0" (
    if exist "%SCRIPT_DIR%%CANDIDATE%" (
        for %%F in ("%SCRIPT_DIR%%CANDIDATE%") do (
            set "%RESULT_VAR%=%%~fF"
        )
        exit /b 0
    )
    if exist "%SCRIPT_DIR%hdd\%CANDIDATE%" (
        for %%F in ("%SCRIPT_DIR%hdd\%CANDIDATE%") do (
            set "%RESULT_VAR%=%%~fF"
        )
        exit /b 0
    )
)

exit /b 1

:derive_received
set "FILENAME=%~1"
set "RESULT_VAR=%~2"
for %%F in ("%FILENAME%") do (
    set "NAME_ONLY=%%~nF"
    set "EXT=%%~xF"
)
if "%EXT%"=="" (
    set "%RESULT_VAR%=%FILENAME%_received"
) else (
    set "%RESULT_VAR%=%NAME_ONLY%_received%EXT%"
)
exit /b 0
