@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3 "%~dp0bootstrap.py" "%~1"
goto finished
:try_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto missing_python
python "%~dp0bootstrap.py" "%~1"
goto finished
:missing_python
echo Python 3.10+ is required. See README.txt and https://www.python.org/downloads/windows/
echo Install normal Python with the launcher, then run install.cmd again.
choice /c OQ /n /m "Open official Python download page [O], or quit [Q]? "
if errorlevel 2 goto python_missing_done
start "" "https://www.python.org/downloads/windows/"
:python_missing_done
set "NETEASE_BETA_RESULT=1"
goto paused
:finished
set "NETEASE_BETA_RESULT=%ERRORLEVEL%"
:paused
if not "%NETEASE_BETA_NO_PAUSE%"=="1" pause
exit /b %NETEASE_BETA_RESULT%
