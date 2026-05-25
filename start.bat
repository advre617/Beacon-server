@echo off
echo Starting Flask Backend Server...
cd /d "C:\Users\klasv\Documents\GitHub\Beacon-server"
echo Current directory: %CD%
echo.

if exist "env\Scripts\activate.bat" (
    echo Activating virtual environment...
    call env\Scripts\activate.bat
) else (
    echo %RED%Virtual environment not found!%NC%
    echo Please create it first: python -m venv venv
    pause
    exit /b 1
)

echo.
echo Running: python app.py
echo.
python app.py

pause