@echo off
REM ==========================================================================
REM  RealGoodSplits - one-click setup for Windows
REM  Creates a local virtual environment and installs everything needed.
REM ==========================================================================
setlocal

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

echo Creating virtual environment in .venv ...
%PY% -m venv .venv
if %errorlevel% neq 0 (
    echo.
    echo ERROR: could not create the virtual environment.
    echo Make sure Python 3.10-3.12 is installed and on your PATH.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo.
echo Installing RealGoodSplits and dependencies (this downloads PyTorch -
echo it can take several minutes the first time) ...
python -m pip install -r requirements.txt
python -m pip install -e .

echo.
echo ==========================================================================
echo  Setup complete!  Double-click run.bat to launch the app.
echo ==========================================================================
pause
