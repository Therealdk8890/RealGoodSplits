@echo off
REM Build a standalone Windows app folder with PyInstaller.
REM Run install_windows.bat first so the virtual environment exists.
setlocal
if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run install_windows.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install "pyinstaller>=6.6"
pyinstaller --noconfirm --clean realgoodsplits.spec
echo.
echo Build complete -> dist\RealGoodSplits\
echo Launch dist\RealGoodSplits\RealGoodSplits.exe
pause
