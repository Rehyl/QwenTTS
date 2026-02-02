@echo off
echo ========================================
echo    Downloading QwenTTS Models
echo    Total Size: ~15GB
echo ========================================
echo.

REM Attiva ambiente virtuale
call venv\Scripts\activate.bat

echo [1/3] Downloading Base Model (Voice Clone)...
echo Destination: ./models/base
huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-Base --local-dir ./models/base
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Download Base fallito!
    pause
    exit /b 1
)

echo.
echo [2/3] Downloading CustomVoice Model (Preset Speakers)...
echo Destination: ./models/custom
huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --local-dir ./models/custom
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Download CustomVoice fallito!
    pause
    exit /b 1
)

echo.
echo [3/3] Downloading VoiceDesign Model (Text Description)...
echo Destination: ./models/design
huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local-dir ./models/design
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Download VoiceDesign fallito!
    pause
    exit /b 1
)

echo.
echo ========================================
echo    Download Completato!
echo ========================================
echo.
echo Modelli salvati in:
echo - ./models/base
echo - ./models/custom
echo - ./models/design
echo.
echo Ora puoi avviare il server con:
echo    .\start.bat
echo.
pause
