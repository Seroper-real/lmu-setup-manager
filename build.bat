@echo off
REM ==============================================
REM Script per creare l'exe di TrackTitan Downloader
REM ==============================================

REM Imposta il nome dell'exe
SET EXE_NAME=lmu-setup-manager
SET VENV_DIR=.venv

REM Crea il venv del progetto se non esiste: il build usa SEMPRE questo python,
REM mai quello globale, cosi' l'exe non dipende da cosa e' installato fuori dal progetto.
IF NOT EXIST %VENV_DIR%\Scripts\python.exe (
    echo Creazione ambiente virtuale in %VENV_DIR% ...
    py -m venv %VENV_DIR%
    IF ERRORLEVEL 1 (
        echo ERRORE: impossibile creare il venv.
        exit /b 1
    )
)

SET PY=%VENV_DIR%\Scripts\python.exe

REM Allinea il venv a requirements.txt (incluso pywebview) e assicura pyinstaller,
REM cosi' l'exe viene sempre generato con le stesse dipendenze bundlate.
%PY% -m pip install -r requirements.txt
IF ERRORLEVEL 1 (
    echo ERRORE: installazione dipendenze fallita.
    exit /b 1
)
%PY% -m pip install pyinstaller
IF ERRORLEVEL 1 (
    echo ERRORE: installazione pyinstaller fallita.
    exit /b 1
)

REM Pulizia cartelle build precedenti
IF EXIST build rmdir /s /q build
IF EXIST dist rmdir /s /q dist
IF EXIST %EXE_NAME%.spec del /f /q %EXE_NAME%.spec

REM Crea l'exe con PyInstaller (sempre tramite il python del venv, non quello del PATH)
REM --collect-all dropbox bundles the SDK's data files (CA cert) needed at runtime
REM --collect-all webview bundles pywebview's own data files (import name is "webview")
REM --windowed: no console subsystem at all - there is no headless path left that needs stdout
REM --icon: same glyph as the GUI's own sidebar logo (assets\icon.ico)
%PY% -m PyInstaller --onefile --windowed --name %EXE_NAME% --icon=assets\icon.ico --paths=src --collect-all dropbox --collect-all webview src\main.py

REM Copia eventuali file esterni nella cartella dist
REM config.json/.env non esistono piu': tutto vive in settings.db sotto %LOCALAPPDATA%.
REM tracks.json resta un file: l'app lo legge in automatico (locale o dal mirror remoto).
xcopy /Y config\tracks.json dist\config\
xcopy /Y /E /I src\gui\web dist\gui\web\

REM Pulizia
IF EXIST build rmdir /s /q build
IF EXIST %EXE_NAME%.spec del /f /q %EXE_NAME%.spec

echo.
echo ===============================
echo Build completata! Esegui da dist\%EXE_NAME%.exe
echo ===============================
pause
