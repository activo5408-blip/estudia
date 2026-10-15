@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo   Canal de Ingles - Instalador Windows
echo ========================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python no esta en PATH.
  echo Instala Python 3.10 o posterior y marca "Add Python to PATH".
  pause
  exit /b 1
)
echo [1/3] Instalando dependencias de Python...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo [2/3] Buscando FFmpeg...
set "FFBIN=G:\INSTALL\!!!Proyectos Yeinier\ffmpeg\bin"
if exist "%FFBIN%\ffmpeg.exe" if exist "%FFBIN%\ffprobe.exe" goto ffmpeg_ok
where ffmpeg >nul 2>nul
if errorlevel 1 goto ffmpeg_manual
for %%I in (ffmpeg.exe) do set "FFEXE=%%~$PATH:I"
for %%I in (ffprobe.exe) do set "FPROBE=%%~$PATH:I"
if not defined FFEXE goto ffmpeg_manual
if not defined FPROBE goto ffmpeg_manual
for %%I in ("%FFEXE%") do set "FFBIN=%%~dpI"
:ffmpeg_ok
set "PATH=%FFBIN%;%PATH%"
echo FFmpeg: "%FFBIN%ffmpeg.exe"
echo FFprobe: "%FFBIN%ffprobe.exe"
"%FFBIN%ffmpeg.exe" -version
echo.
echo [3/3] Instalacion terminada.
echo Ejecuta ABRIR_CANAL_INGLES.bat para abrir el programa.
pause
exit /b 0
:ffmpeg_manual
echo No se encontro FFmpeg.
echo Coloca ffmpeg.exe y ffprobe.exe en:
echo G:\INSTALL\!!!Proyectos Yeinier\ffmpeg\bin
echo o agrega la carpeta bin de FFmpeg al PATH.
pause
exit /b 1
:error
echo ERROR instalando las dependencias Python.
pause
exit /b 1
