@echo off
setlocal
cd /d "%~dp0"
echo.
echo ==========================================================
echo   COMPILAR Y SUBIR CON PLATFORMIO
echo   (solo necesario si modificaste el firmware)
echo ==========================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\compilar_y_subir.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
