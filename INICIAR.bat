@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0pc\.venv\Scripts\python.exe"
title Plataforma estabilizadora de pelota
if not exist "%PYTHON%" goto :sin_instalar
"%PYTHON%" "%~dp0pc\main.py" %*
set "RESULT=%ERRORLEVEL%"
echo.
echo La aplicacion termino con codigo %RESULT%.
pause
exit /b %RESULT%
:sin_instalar
echo.
echo Todavia no esta instalada la aplicacion.
echo Ejecuta INSTALAR.bat una vez y volve a intentar.
pause
exit /b 1
