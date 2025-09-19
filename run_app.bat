@echo off
REM Batch file to run the Simple Data Checker Flask application
REM This script activates the conda environment and starts the Flask app

cd /d "%~dp0"
echo Starting Simple Data Checker...
echo.

REM Check if conda is available
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo Conda not found in PATH. Trying to locate conda...
    if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" (
        set "CONDA_PATH=%USERPROFILE%\miniconda3\Scripts\conda.exe"
    ) else if exist "%USERPROFILE%\anaconda3\Scripts\conda.exe" (
        set "CONDA_PATH=%USERPROFILE%\anaconda3\Scripts\conda.exe"
    ) else if exist "C:\ProgramData\miniconda3\Scripts\conda.exe" (
        set "CONDA_PATH=C:\ProgramData\miniconda3\Scripts\conda.exe"
    ) else if exist "C:\ProgramData\anaconda3\Scripts\conda.exe" (
        set "CONDA_PATH=C:\ProgramData\anaconda3\Scripts\conda.exe"
    ) else (
        echo Conda installation not found. Please install Miniconda or Anaconda.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )
    call "%CONDA_PATH%" activate base
) else (
    REM Activate the base conda environment
    call conda activate base
)

REM Start the Flask application in the background
echo Starting Flask server...
start /b python app.py

REM Wait a moment for the server to start
timeout /t 3 /nobreak >nul

REM Open the default browser to the application
echo Opening browser...
start http://localhost:5000

REM Keep the window open to show server logs
echo.
echo Simple Data Checker is running!
echo Server logs will appear below.
echo Close this window to stop the application.
echo.
echo Press Ctrl+C to stop the server, or close this window.
echo.

REM Wait for the Python process to finish
python app.py

REM Keep the window open if there's an error
if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
) 