@echo off
setlocal
cd /d "%~dp0"
set "PATH=G:\INSTALL\!!!Proyectos Yeinier\ffmpeg\bin;%PATH%"
where python >nul 2>nul
if errorlevel 1 (
 echo No se encuentra Python en PATH.
 pause
 exit /b 1
)
python programa.py
if errorlevel 1 (
 echo.
 echo El programa se cerro con un error.
 pause
)
