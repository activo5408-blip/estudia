@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 (
  echo ERROR: No se pudo entrar en la carpeta del proyecto.
  echo Carpeta esperada: "%~dp0"
  pause
  exit /b 1
)
if not exist "%~dp0crear_video.py" (
  echo ERROR: No se encuentra crear_video.py junto a este archivo.
  echo Vuelve a extraer el ZIP completo en una carpeta normal.
  pause
  exit /b 1
)
if "%~1"=="" (
  set /p "LECCION=Ruta del JSON de la leccion [lecciones\leccion-01.json]: "
  if not defined LECCION set "LECCION=lecciones\leccion-01.json"
) else (
  set "LECCION=%~1"
)
if not exist "%LECCION%" (
  echo.
  echo ERROR: No se encuentra el archivo JSON: "%LECCION%"
  echo Comprueba que la carpeta lecciones esta dentro del proyecto.
  pause
  exit /b 1
)
python "%~dp0crear_video.py" "%LECCION%"
if errorlevel 1 (
  echo.
  echo El generador termino con un error. Revisa los mensajes anteriores.
)
pause
