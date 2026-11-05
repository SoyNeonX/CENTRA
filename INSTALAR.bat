@echo off
setlocal
cd /d "%~dp0"
echo.
echo ==========================================================
echo   CENTRA - INSTALADOR - AGUILAS IMPERIALES
echo ==========================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\instalar.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
    echo La instalacion no termino correctamente.
    echo Revisa el mensaje de arriba.
    pause
    exit /b %RESULT%
)
echo Listo. Ahora podes usar CENTRA.bat o el acceso directo del escritorio.
pause
exit /b 0
