@echo off
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python app.py
pause
exit /b

:failed
echo Dependency setup failed. Check the error above.
pause
exit /b 1
