@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo   Voz clonada gratis (Chatterbox)
echo ========================================
echo Necesita Python 3.11 (con 3.12 o superior puede fallar).
python --version
echo.
python -m pip install --upgrade pip
python -m pip install "setuptools<81" torch torchaudio chatterbox-tts edge-tts Pillow
if errorlevel 1 (
  echo.
  echo ERROR instalando. Copia el mensaje y revisalo.
  pause
  exit /b 1
)
echo.
echo Listo. Copia tu audio de mujer (5-10 segundos) a esta carpeta con el nombre voz_mujer.mp3
echo Con tarjeta NVIDIA conviene instalar PyTorch con CUDA desde pytorch.org.
pause
