@echo off
REM Stops the office system running in the background (it also stops when the PC shuts down).
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*manage.py runserver 127.0.0.1:8765*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo The school office system has been stopped.
timeout /t 3 >nul
