# Prepara un paquete offline dentro de la carpeta "paquete".
# Se ejecuta desde PREPARAR_PENDRIVE.bat y necesita internet en esta PC.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$pcDir = Join-Path $root "pc"
$packageDir = Join-Path $root "paquete"
$wheelsDir = Join-Path $packageDir "wheels"
$installersDir = Join-Path $packageDir "instaladores"
$targetPython = "3.12.10"
$targetMajorMinor = "3.12"
$targetAbi = "cp312"
$targetPlatform = "win_amd64"

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "  PREPARAR PAQUETE OFFLINE PARA PENDRIVE" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "  Esta PC necesita internet para descargar los componentes."

$python = $null
$pythonPrefix = @()
$pythonVersion = ""
$pythonBits = 0
$localPython312 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$candidates = @(
    @{ Exe = "py"; Prefix = @("-3.12") },
    @{ Exe = $localPython312; Prefix = @() },
    @{ Exe = "python"; Prefix = @() }
)
foreach ($candidate in $candidates) {
    $exePath = $null
    $command = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
    if ($command) {
        $exePath = $command.Source
    } elseif (Test-Path $candidate.Exe) {
        $exePath = (Resolve-Path $candidate.Exe).Path
    } else {
        continue
    }
    $probe = "import sys,struct; print(str(sys.version_info[0])+'.'+str(sys.version_info[1])+'|'+str(struct.calcsize('P')*8))"
    try {
        $output = & $exePath @($candidate.Prefix) -c $probe 2>$null
    } catch {
        continue
    }
    if ($LASTEXITCODE -eq 0 -and $output) {
        $text = [string]($output | Select-Object -First 1)
        $parts = $text.Trim().Split("|")
        if ($parts.Count -eq 2) {
            $python = $exePath
            $pythonPrefix = $candidate.Prefix
            $pythonVersion = $parts[0]
            $pythonBits = [int]$parts[1]
            break
        }
    }
}
if (-not $python) {
    Write-Host "ERROR: necesitas Python instalado en esta PC para preparar el paquete." -ForegroundColor Red
    exit 1
}
if ($pythonVersion -ne $targetMajorMinor -or $pythonBits -ne 64) {
    Write-Host "ERROR: el paquete offline se prepara con Python $targetMajorMinor x64." -ForegroundColor Red
    Write-Host "Esta PC tiene Python $pythonVersion de $pythonBits bits." -ForegroundColor Yellow
    Write-Host "Instala Python $targetMajorMinor x64 en esta PC y volve a intentar." -ForegroundColor Yellow
    exit 1
}

Write-Step "Creando carpetas del paquete"
New-Item -ItemType Directory -Force -Path $packageDir | Out-Null
if (Test-Path $wheelsDir) {
    Remove-Item -LiteralPath $wheelsDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $wheelsDir | Out-Null
New-Item -ItemType Directory -Force -Path $installersDir | Out-Null
Write-Host "    $packageDir"

Write-Step "Descargando y construyendo ruedas para Python $pythonVersion x64"
Write-Host "    Esto puede tardar unos minutos..." -ForegroundColor DarkGray
$requirements = Join-Path $pcDir "requirements.txt"
$flashRequirements = Join-Path $pcDir "tools\requirements-flash.txt"
# pip wheel tambien genera la rueda de esptool, que suele publicarse solo
# como codigo fuente. Las dependencias binarias se conservan.
& $python @pythonPrefix -m pip wheel `
    --disable-pip-version-check `
    --wheel-dir $wheelsDir `
    -r $requirements `
    -r $flashRequirements
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: no se pudieron preparar las librerias." -ForegroundColor Red
    Write-Host "Revisa la conexion a internet y volve a intentar." -ForegroundColor Yellow
    exit 1
}
$wheelCount = @(Get-ChildItem $wheelsDir -Filter "*.whl").Count
Write-Host "    $wheelCount ruedas disponibles." -ForegroundColor Green

Write-Step "Incluyendo instalador de Python $targetPython x64"
$pythonExeName = "python-$targetPython-amd64.exe"
$pythonInstaller = Join-Path $installersDir $pythonExeName
$pythonUrl = "https://www.python.org/ftp/python/$targetPython/$pythonExeName"
if ((Test-Path $pythonInstaller) -and ((Get-Item $pythonInstaller).Length -gt 20000000)) {
    Write-Host "    Ya estaba descargado: $pythonInstaller" -ForegroundColor Green
} else {
    Write-Host "    Descargando $pythonUrl" -ForegroundColor DarkGray
    $downloadCode = "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2]); print('descargado')"
    & $python @pythonPrefix -c $downloadCode $pythonUrl $pythonInstaller
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $pythonInstaller)) {
        Write-Host "    AVISO: no se pudo descargar el instalador de Python." -ForegroundColor Yellow
        Write-Host "    El resto del paquete queda util si la PC de la escuela ya tiene Python." -ForegroundColor Yellow
        Write-Host "    Tambien podes descargarlo desde python.org y copiarlo a:" -ForegroundColor Yellow
        Write-Host "      $installersDir" -ForegroundColor Yellow
    } else {
        Write-Host "    Instalador de Python incluido." -ForegroundColor Green
    }
}

Write-Step "Creando metadatos y LEEME del paquete"
$created = Get-Date -Format "yyyy-MM-dd HH:mm"
@"
target_python=$targetMajorMinor
platform=$targetPlatform
python_installer=$pythonExeName
created=$created
"@ | Set-Content -Path (Join-Path $packageDir "entorno.txt") -Encoding ASCII

$firmware = Join-Path $root "firmware\prebuilt\plataforma_pelota_esp32.bin"
$firmwareLine = "Firmware precompilado: NO ENCONTRADO"
if (Test-Path $firmware) {
    $firmwareLine = "Firmware precompilado: firmware\prebuilt\plataforma_pelota_esp32.bin"
}

$readme = @"
PLATAFORMA ESTABILIZADORA DE PELOTA - PAQUETE PARA PENDRIVE
===========================================================

Este paquete fue preparado para Windows x64 y Python $targetMajorMinor.
Fecha: $created

QUE HACER AHORA
---------------
1. Copia TODA la carpeta del proyecto "plataforma-pelota" al pendrive.
   Incluye esta carpeta "paquete".
2. En la PC de la escuela, conecta el pendrive y abre la carpeta.
3. Si la PC no tiene Python, ejecuta primero:
      paquete\instaladores\$pythonExeName
   Marca "Add python.exe to PATH".
4. Ejecuta INSTALAR.bat. Detecta el paquete offline y no necesita internet.
5. Ejecuta SUBIR_FIRMWARE.bat y elegi el COM del ESP32.
6. Ejecuta ELEGIR_DISPOSITIVOS.bat si hace falta elegir camara y COM.
7. Ejecuta INICIAR.bat.

Si hay internet en la escuela, tambien podes ejecutar INSTALAR.bat sin el
paquete offline; el instalador descarga las dependencias automaticamente.

NO se necesita PlatformIO en la escuela para grabar el firmware precompilado.
El firmware se graba con esptool (ya viene en el entorno instalado).

$firmwareLine
Target Python: $targetMajorMinor
Target wheels: $wheelCount archivos en paquete\wheels
"@
$readme | Set-Content -Path (Join-Path $packageDir "LEEME_PENDRIVE.txt") -Encoding ASCII

$totalBytes = 0
Get-ChildItem $packageDir -Recurse -File | ForEach-Object { $totalBytes += $_.Length }
$totalMB = [math]::Round($totalBytes / 1MB, 1)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  PAQUETE OFFLINE LISTO" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Carpeta: $packageDir"
Write-Host "  Tamano aproximado: $totalMB MB"
Write-Host "  Ruedas: $wheelCount"
Write-Host "  Instalador Python incluido: $(Test-Path $pythonInstaller)"
Write-Host ""
Write-Host "  Copia toda la carpeta del proyecto al pendrive, no solo 'paquete'."
Write-Host "  En la escuela: INSTALAR.bat -> SUBIR_FIRMWARE.bat -> ELEGIR_DISPOSITIVOS.bat -> INICIAR.bat"
Write-Host "  Lee paquete\LEEME_PENDRIVE.txt para el paso a paso." -ForegroundColor Cyan
Write-Host ""
exit 0
