@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0pc\.venv\Scripts\python.exe"
if not exist "%PYTHON%" goto :sin_instalar
echo.
echo Abriendo el selector de camara y puerto serial...
"%PYTHON%" "%~dp0pc\main.py" --setup-devices
echo.
echo El selector se cerro. Ejecuta INICIAR.bat para probar la aplicacion.
pause
exit /b 0
:sin_instalar
echo.
echo Ejecuta INSTALAR.bat antes de configurar los dispositivos.
pause
exit /b 1
