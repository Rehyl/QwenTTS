@echo off
echo ========================================
echo    QwenTTS All-in-One
echo    Starting server...
echo ========================================
echo.

cd /d "%~dp0"

REM Attiva ambiente virtuale
call venv\Scripts\activate.bat

REM Avvia server Flask
python backend\app.py

pause
