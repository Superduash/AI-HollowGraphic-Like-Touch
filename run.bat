@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem Prefer Python 3.12 on Windows 11.
set "PYEXE="
set "PYVER="
for %%V in (3.12 3.11 3.10 3) do (
  if not defined PYEXE (
    py -%%V -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      set "PYEXE=py -%%V"
      set "PYVER=%%V"
    )
  )
)

if not defined PYEXE (
  echo.
  echo ERROR: Python launcher 'py' not found.
  echo Install Python 3.12+ from https://python.org and re-run.
  echo.
  pause
  exit /b 1
)

echo Using Python %PYVER% (%PYEXE%)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYEXE% -m venv .venv
  if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error

set "REQ_HASH="
for /f "usebackq delims=" %%H in (`python -c "import hashlib;print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"`) do set "REQ_HASH=%%H"
set "HASH_FILE=.venv\.requirements.sha256"
set "OLD_HASH="
if exist "%HASH_FILE%" (
  set /p OLD_HASH=<"%HASH_FILE%"
)

if "%REQ_HASH%"=="%OLD_HASH%" (
  echo Requirements already installed. Skipping pip install.
) else (
  echo Upgrading pip tooling...
  python -m pip install --upgrade pip setuptools wheel
  if errorlevel 1 goto :error

  echo Installing requirements...
  python -m pip install -r requirements.txt
  if errorlevel 1 goto :error

  >"%HASH_FILE%" echo %REQ_HASH%
)

echo Launching Windows Hover...
python app.py
if errorlevel 1 goto :error

exit /b 0

:error
echo.
echo ERROR: Setup or launch failed. See messages above.
echo.
pause
exit /b 1
