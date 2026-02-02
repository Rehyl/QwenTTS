@echo off
echo ========================================
echo    QwenTTS Setup Script
echo    Python 3.13.10 with venv
echo ========================================
echo.

REM Controlla se Python è installato
python --version >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Python non trovato! Installare Python 3.13.10 da python.org
    pause
    exit /b 1
)

echo Verifica versione Python...
python --version

echo.
echo [1/5] Creazione ambiente virtuale 'venv'...
python -m venv venv
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Creazione ambiente virtuale fallita!
    pause
    exit /b 1
)

echo.
echo [2/5] Attivazione ambiente virtuale...
call venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Attivazione ambiente fallita!
    pause
    exit /b 1
)

echo.
echo [3/5] Aggiornamento pip...
python -m pip install --upgrade pip

echo.
echo [4/5] Installazione dipendenze base...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Installazione dipendenze fallita!
    pause
    exit /b 1
)

echo.
echo [4.5/5] Controllo e installazione FFmpeg (automatico)...
if not exist "venv\Scripts\ffmpeg.exe" (
    echo FFmpeg non trovato. Download in corso...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'ffmpeg.zip'"
    
    echo Estrazione archivio...
    powershell -Command "Expand-Archive -Path 'ffmpeg.zip' -DestinationPath 'ffmpeg_temp' -Force"
    
    echo Installazione in venv\Scripts...
    for /r "ffmpeg_temp" %%f in (ffmpeg.exe) do copy "%%f" "venv\Scripts\" /Y >nul
    for /r "ffmpeg_temp" %%f in (ffprobe.exe) do copy "%%f" "venv\Scripts\" /Y >nul
    
    echo Pulizia file temporanei...
    del ffmpeg.zip
    rmdir /s /q ffmpeg_temp
    
    echo FFmpeg installato correttamente!
) else (
    echo FFmpeg gia' presente.
)

echo.
echo [5/5] Installazione Flash Attention 2 (opzionale, può richiedere tempo)...
echo Premere Ctrl+C per saltare, altrimenti attendere...
timeout /t 5
pip install -U flash-attn --no-build-isolation
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Flash Attention non installato - verrà usato fallback automatico
)

echo.
echo.
echo [6/6] Installazione Hugging Face CLI...
pip install "huggingface_hub[cli]<1.0"

echo.
echo ========================================
echo    Setup Completato!
echo ========================================
echo.
echo PROSSIMI PASSI:
echo.
echo 1. Scarica i modelli eseguendo:
echo    .\download_models.bat
echo.
echo 2. Avvia il server con:
echo    .\start.bat
echo.
echo 3. Apri il browser su:
echo    http://localhost:5000
echo.
pause
