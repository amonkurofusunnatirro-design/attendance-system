@echo off
cd /d %~dp0
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto python_failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not defined FACEATTEND_MODEL set FACEATTEND_MODEL=buffalo_l
echo Face model: %FACEATTEND_MODEL%
if not defined FACEATTEND_TG_TOKEN echo Telegram is disabled: FACEATTEND_TG_TOKEN is not set.
if not defined FACEATTEND_TG_ADMIN_CHAT echo Admin Telegram alerts are disabled: FACEATTEND_TG_ADMIN_CHAT is not set.
.venv\Scripts\python app.py
pause
exit /b

:failed
echo Dependency setup failed. Check the error above.
pause
exit /b 1

:python_failed
echo Python 3 was not found. Install Python 3.10 or newer and enable the Python launcher or add Python to PATH.
pause
exit /b 1
