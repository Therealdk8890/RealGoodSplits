@echo off
REM Launch the RealGoodSplits desktop app from the local virtual environment.
setlocal
if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run install_windows.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
python -m realgoodsplits
