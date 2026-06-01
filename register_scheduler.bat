@echo off
chcp 65001 > nul
echo ============================================
echo  작업 스케줄러 등록 시작
echo  AutoRefresh_EdgeMonitor
echo  실행 시각: 월/목/금 오전 8시
echo ============================================
echo.

powershell -ExecutionPolicy Bypass -Command ^
"$action = New-ScheduledTaskAction -Execute 'C:\Users\03477\Downloads\ens\run_auto_refresh.bat'; ^
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Thursday,Friday -At '08:00'; ^
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 12) -StartWhenAvailable -RunOnlyIfNetworkAvailable; ^
Register-ScheduledTask -TaskName 'AutoRefresh_EdgeMonitor' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force"

if %errorlevel% == 0 (
    echo.
    echo ============================================
    echo  등록 완료!
    echo  작업 이름 : AutoRefresh_EdgeMonitor
    echo  실행 파일 : D:\Downloads\run_auto_refresh.bat
    echo  실행 요일 : 월요일, 목요일, 금요일
    echo  실행 시각 : 오전 08:00
    echo ============================================
) else (
    echo.
    echo [오류] 스케줄러 등록에 실패했습니다.
    echo 관리자 권한으로 실행했는지 확인하세요.
)

echo.
pause
