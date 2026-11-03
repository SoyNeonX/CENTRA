@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0pc\.venv\Scripts\python.exe"
title Subir firmware al ESP32
if not exist "%PYTHON%" goto :sin_instalar
"%PYTHON%" "%~dp0pc\tools\flash_firmware.py" %*
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
:sin_instalar
echo.
echo Ejecuta INSTALAR.bat antes de grabar el firmware.
pause
exit /b 1
