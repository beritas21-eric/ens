@echo off
echo ============================================
echo  AutoRefresh_EdgeMonitor
echo ============================================
echo.

powershell -ExecutionPolicy Bypass -Command "$action = New-ScheduledTaskAction -Execute 'C:\Users\03477\Downloads\ens\run_auto_refresh.bat'; $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday -At '08:30'; $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 12) -StartWhenAvailable -RunOnlyIfNetworkAvailable; Register-ScheduledTask -TaskName 'AutoRefresh_EdgeMonitor' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force"

if %errorlevel% == 0 (
    echo.
    echo ============================================
    echo  OK: AutoRefresh_EdgeMonitor
    echo  File: C:\Users\03477\Downloads\ens\run_auto_refresh.bat
    echo  Days: Tuesday, Wednesday
    echo  Time: 08:30
    echo ============================================
) else (
    echo.
    echo [ERROR] Failed to register scheduler.
    echo Please run as Administrator.
)

echo.
pause
