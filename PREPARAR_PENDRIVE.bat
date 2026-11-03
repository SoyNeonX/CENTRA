@echo off
setlocal
cd /d "%~dp0"
echo.
echo ==========================================================
echo   PREPARAR PAQUETE OFFLINE PARA LLEVAR EN PENDRIVE
echo   Necesita internet en esta PC.
echo ==========================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\preparar_pendrive.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
