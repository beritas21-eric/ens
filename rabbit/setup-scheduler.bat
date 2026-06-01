@echo off
:: ============================================================
::  RabbitMQ Monitor - Task Scheduler Registration
::  Run this file as Administrator (right-click -> Run as admin)
::  Schedule: Mon-Fri at 08:00
:: ============================================================
setlocal EnableDelayedExpansion

set TASK_NAME=RabbitMQ-Monitor-AutoStart
set START_TIME=08:00
set BAT_FILE=%~dp0start-rabbitmq-monitor.bat
schtasks /delete /tn "RabbitMQ-Monitor-AutoStart" /f > nul 2>&1
echo.
echo  ====================================================
echo   RabbitMQ Monitor - Task Scheduler Setup
echo  ====================================================
echo.

:: -- Check administrator privileges -----------------------
net session > nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Administrator privileges required.
    echo.
    echo  Please right-click this file and select
    echo  "Run as administrator".
    echo.
    pause
    exit /b 1
)
echo  [OK] Running as Administrator

:: -- Check batch file exists ------------------------------
if not exist "%BAT_FILE%" (
    echo  [ERROR] File not found:
    echo          %BAT_FILE%
    echo.
    pause
    exit /b 1
)
echo  [OK] Batch file found: %BAT_FILE%

:: -- Delete existing task (ignore error if not exists) ----
echo.
echo  [1/2] Removing existing task (if any)...
schtasks /delete /tn "%TASK_NAME%" /f > nul 2>&1
echo        Done.

:: -- Register new scheduled task --------------------------
echo  [2/2] Registering scheduled task...
echo.
echo        Name     : %TASK_NAME%
echo        Command  : %BAT_FILE%
echo        Schedule : Mon-Fri at %START_TIME%
echo.

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "cmd.exe /c \"%BAT_FILE%\"" ^
    /sc WEEKLY ^
    /d MON,TUE,WED,THU,FRI ^
    /st %START_TIME% ^
    /f

set REG_RESULT=%errorlevel%

echo.
if %REG_RESULT% equ 0 (
    echo  ====================================================
    echo   SUCCESS - Task registered!
    echo  ====================================================
    echo.
    echo   Schedule : Mon-Fri at %START_TIME%
    echo   Task name: %TASK_NAME%
    echo.
    echo   [How to verify]
    echo   Open Task Scheduler ^> Task Scheduler Library
    echo   ^> "%TASK_NAME%"
    echo.
    echo   [Run now to test]
    echo   schtasks /run /tn "%TASK_NAME%"
    echo.
    echo   [Remove task]
    echo   schtasks /delete /tn "%TASK_NAME%" /f
    echo.
) else (
    echo  ====================================================
    echo   FAILED - Error code: %REG_RESULT%
    echo  ====================================================
    echo.
    echo   Try running this command manually in admin CMD:
    echo.
    echo   schtasks /create /tn "%TASK_NAME%" ^
    echo     /tr "cmd.exe /c \"%BAT_FILE%\"" ^
    echo     /sc WEEKLY /d MON,TUE,WED,THU,FRI ^
    echo     /st %START_TIME% /f
    echo.
)

pause
endlocal
exit /b %REG_RESULT%
