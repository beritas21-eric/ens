@echo off
setlocal EnableDelayedExpansion
set PORT=8080
set SCRIPT_DIR=%~dp0
set SERVER_PY=%SCRIPT_DIR%rabbitmq-server.py
set BROWSER_URL=http://localhost:%PORT%
set LOG_FILE=%SCRIPT_DIR%rabbitmq-monitor.log

echo.
echo  ====================================================
echo   RabbitMQ Monitor  -  Starting...
echo   %DATE%  %TIME%
echo  ====================================================
echo.

set PYTHON_CMD=
for %%P in (python py python3) do (
    if "!PYTHON_CMD!"=="" (
        %%P --version > nul 2>&1
        if !errorlevel! == 0 set PYTHON_CMD=%%P
    )
)
if "!PYTHON_CMD!"=="" (
    echo  [ERROR] Python not found.
    echo          Install Python 3 from https://www.python.org/
    pause
    exit /b 1
)
echo  [OK] Python  : !PYTHON_CMD!

if not exist "%SERVER_PY%" (
    echo  [ERROR] Server file not found: %SERVER_PY%
    pause
    exit /b 1
)
echo  [OK] Server  : %SERVER_PY%

echo.
echo  [1/3] Checking port %PORT%...
set KILLED=0

for /f %%P in ('powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique"') do (
    if "%%P"=="0" (
        echo         [SKIP] PID 0 is System.
    ) else if "%%P"=="4" (
        echo         [SKIP] PID 4 is System.
    ) else (
        echo         Killing PID %%P ...
        taskkill /PID %%P /F > nul 2>&1
        if !errorlevel! == 0 (
            set KILLED=1
        ) else (
            echo  [WARN] Could not kill PID %%P
        )
    )
)

if "!KILLED!"=="1" (
    echo         Old server stopped. Waiting...
    timeout /t 2 /nobreak > nul
) else (
    echo         No existing server on port %PORT%.
)

echo.
echo  [2/3] Starting server...
echo [%DATE% %TIME%] Server started >> "%LOG_FILE%"
start "RabbitMQ-Monitor-Server" /MIN !PYTHON_CMD! "%SERVER_PY%"

set /a WAIT=0
:WAIT_LOOP
    timeout /t 1 /nobreak > nul
    set /a WAIT+=1
    powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue" > nul 2>&1
    if !errorlevel! == 0 goto SERVER_READY
    if !WAIT! geq 10 goto SERVER_TIMEOUT
goto WAIT_LOOP

:SERVER_TIMEOUT
echo  [WARN] Server did not start within !WAIT! seconds.
echo         Check log: %LOG_FILE%
goto OPEN_BROWSER

:SERVER_READY
echo         Server ready in !WAIT! sec.

:OPEN_BROWSER
echo.
echo  [3/3] Opening browser at %BROWSER_URL% ...
set EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
set CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe
set CHROME2=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
if exist "!EDGE!"    ( start "" "!EDGE!"    %BROWSER_URL% & goto DONE )
if exist "!CHROME!"  ( start "" "!CHROME!"  %BROWSER_URL% & goto DONE )
if exist "!CHROME2!" ( start "" "!CHROME2!" %BROWSER_URL% & goto DONE )
start "" %BROWSER_URL%

:DONE
echo.
echo  ====================================================
echo   Done!  Browser opened at %BROWSER_URL%
echo   Log: %LOG_FILE%
echo  ====================================================
echo.
timeout /t 3 /nobreak > nul
endlocal
exit /b 0
