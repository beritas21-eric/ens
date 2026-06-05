@echo off
echo ============================================
echo  AutoRefresh_EdgeMonitor
echo ============================================
echo.

powershell -ExecutionPolicy Bypass -Command "$action = New-ScheduledTaskAction -Execute 'D:\Downloads\run_auto_refresh.bat'; $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '08:00'; $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 12) -StartWhenAvailable -RunOnlyIfNetworkAvailable; Register-ScheduledTask -TaskName 'AutoRefresh_EdgeMonitor' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force"

if %errorlevel% == 0 (
    echo.
    echo ============================================
    echo  OK: AutoRefresh_EdgeMonitor
    echo  File: D:\Downloads\run_auto_refresh.bat
    echo  Days: Monday ~ Friday
    echo  Time: 08:00
    echo ============================================
) else (
    echo.
    echo [ERROR] Failed to register scheduler.
    echo Please run as Administrator.
)

echo.
pause
