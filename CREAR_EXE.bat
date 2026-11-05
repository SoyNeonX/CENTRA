@echo off
setlocal
cd /d "%~dp0"
title Crear CENTRA.exe

set "PYTHON=%~dp0pc\.venv\Scripts\python.exe"
if not exist "%PYTHON%" goto :sin_entorno

echo.
echo === 1/2 Comprobando PyInstaller ===
"%PYTHON%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 goto :crear_lanzador

echo.
echo === 2/2 Empaquetando la aplicacion ===
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --console --name CENTRA --icon "%~dp0docs\app_icon.ico" --paths "%~dp0pc" --hidden-import tk_app --add-data "%~dp0pc\config.json;." "%~dp0pc\main.py"
if errorlevel 1 goto :crear_lanzador

echo.
echo === Copiando el ejecutable a la raiz ===
copy /Y "%~dp0dist\CENTRA.exe" "%~dp0CENTRA.exe" >nul
if errorlevel 1 goto :error

echo.
echo LISTO: %~dp0CENTRA.exe
echo Abri la app con CENTRA.bat (OpenCV o Tkinter).
echo Tambien podes probar la simulacion desde ese menu.
pause
exit /b 0

:sin_entorno
echo.
echo Falta pc\.venv. Ejecuta INSTALAR.bat primero.
pause
exit /b 1

:crear_lanzador
echo.
echo PyInstaller no esta instalado o fallo.
echo Creando CENTRA.exe como lanzador de la app instalada...
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" goto :error
"%CSC%" /nologo /target:winexe /out:"%~dp0CENTRA.exe" /r:System.Windows.Forms.dll "%~dp0pc\tools\launcher.cs"
if errorlevel 1 goto :error
echo.
echo LISTO (lanzador): %~dp0CENTRA.exe
echo Este lanzador requiere pc\.venv creado por INSTALAR.bat.
echo Usalo desde CENTRA.bat.
pause
exit /b 0

:error
echo.
echo ERROR al crear el ejecutable. Lee el mensaje anterior.
pause
exit /b 1
