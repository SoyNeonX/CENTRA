@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON=%~dp0pc\.venv\Scripts\python.exe"
set "MAIN=%~dp0pc\main.py"
set "EXE=%~dp0CENTRA.exe"
set "DIAG=%~dp0pc\tools\diagnose.py"
set "ARGS="

:menu
echo.
echo ============================================================
echo   CENTRA - AGUILAS IMPERIALES
echo   Plataforma estabilizadora de pelota
echo ============================================================
echo   1. Abrir CENTRA (OpenCV)
echo   2. Abrir CENTRA (Tkinter)
echo   3. Simular OpenCV
echo   4. Simular Tkinter
echo   5. Configurar camara y puerto USB
echo   6. Verificar instalacion
echo   7. Firmware / ESP32
echo   8. Salir
echo.
choice /C 12345678 /N /M "  Opcion: "
if errorlevel 8 goto :fin
if errorlevel 7 goto :firmware
if errorlevel 6 goto :verify
if errorlevel 5 goto :config
if errorlevel 4 goto :sim_tk
if errorlevel 3 goto :sim_cv
if errorlevel 2 goto :tk
goto :opencv

:opencv
set "ARGS="
goto :run

:tk
set "ARGS=--tk"
goto :run

:sim_cv
set "ARGS=--sim"
goto :run

:sim_tk
set "ARGS=--tk --sim"
goto :run

:config
set "ARGS=--setup-devices"
goto :run

:run
if exist "%EXE%" goto :run_exe
if not exist "%PYTHON%" goto :sin_instalar
"%PYTHON%" "%MAIN%" %ARGS%
goto :after_run

:run_exe
"%EXE%" %ARGS%
goto :after_run

:verify
if not exist "%PYTHON%" goto :sin_instalar
"%PYTHON%" "%DIAG%"
goto :after_run

:firmware
call "%~dp0FIRMWARE.bat"
goto :menu

:after_run
echo.
pause
goto :menu

:sin_instalar
echo.
echo No hay pc\.venv ni CENTRA.exe.
echo Ejecuta INSTALAR.bat primero.
pause
goto :menu

:fin
endlocal
exit /b 0
