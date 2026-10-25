@echo off
REM ==================================================================
REM  Nexora School Office - one-time setup.  Double-click this file.
REM  Needs Python 3.10 or newer and an internet connection (once).
REM  Progress is written to setup_log.txt in this folder.
REM  Safe to run again: it never deletes your records.
REM ==================================================================
cd /d "%~dp0"
set LOG=%~dp0setup_log.txt
echo Setup started %DATE% %TIME% > "%LOG%"
echo.
echo  Setting up Nexora School Office...
echo  (this takes a minute or two the first time)
echo.

set PY=
where python >nul 2>&1 && python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set PY=python
if not defined PY ( where py >nul 2>&1 && py -3 -c "import sys" >nul 2>&1 && set PY=py -3 )
if not defined PY (
  echo STEP FAILED: Python 3.10+ not found. >> "%LOG%"
  echo  Python was not found. Install it from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" on the first screen, then run this again.
  pause
  exit /b 1
)
%PY% --version >> "%LOG%" 2>&1

echo  [1/5] Preparing Python...
if not exist venv\Scripts\python.exe %PY% -m venv venv >> "%LOG%" 2>&1 || goto :fail
set VPY=venv\Scripts\python.exe

echo  [2/5] Installing Django (needs internet)...
%VPY% -m pip install --upgrade pip >> "%LOG%" 2>&1
%VPY% -m pip install -r requirements.txt >> "%LOG%" 2>&1 || goto :fail

echo  [3/5] Creating the database...
%VPY% manage.py migrate --noinput >> "%LOG%" 2>&1 || goto :fail

echo  [4/5] Adding the 13 classes...
%VPY% manage.py load_school_data >> "%LOG%" 2>&1 || goto :fail

echo  [5/5] Making the desktop icon...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1" >> "%LOG%" 2>&1

echo SETUP COMPLETE >> "%LOG%"
echo.
echo  ==============================================================
echo   Done! Double-click "Nexora School Office" on your desktop.
echo   The first time, it asks you to choose the admin password.
echo  ==============================================================
echo.
pause
exit /b 0

:fail
echo STEP FAILED - see messages above >> "%LOG%"
echo.
echo  Setup stopped. Open setup_log.txt in this folder to see why.
pause
exit /b 1
