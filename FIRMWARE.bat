@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON=%~dp0pc\.venv\Scripts\python.exe"
set "FLASH=%~dp0pc\tools\flash_firmware.py"

:menu
echo.
echo ============================================================
echo   CENTRA - FIRMWARE ESP32-WROOM
echo ============================================================
echo   1. Subir firmware precompilado
echo   2. Compilar y subir con PlatformIO
echo   3. Monitor serie (115200)
echo   4. Volver
echo.
choice /C 1234 /N /M "  Opcion: "
if errorlevel 4 exit /b 0
if errorlevel 3 goto :monitor
if errorlevel 2 goto :compile
goto :upload

:upload
if not exist "%PYTHON%" goto :sin_instalar
"%PYTHON%" "%FLASH%"
pause
goto :menu

:compile
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\compilar_y_subir.ps1"
pause
goto :menu

:monitor
where pio >nul 2>nul
if errorlevel 1 (
    echo PlatformIO no esta en PATH.
    pause
    goto :menu
)
pio device monitor -b 115200
pause
goto :menu

:sin_instalar
echo.
echo Falta pc\.venv. Ejecuta INSTALAR.bat primero.
pause
goto :menu
