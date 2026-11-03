# Compila el firmware con PlatformIO y lo sube al ESP32.
# Se usa solo si se modifica el codigo fuente del firmware.

param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$firmwareDir = Join-Path $root "firmware"

function Find-Pio {
    $command = Get-Command pio -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $localPio = Join-Path $env:USERPROFILE ".platformio\penv\Scripts\platformio.exe"
    if (Test-Path $localPio) { return $localPio }
    return $null
}

$pio = Find-Pio
if (-not $pio) {
    Write-Host ""
    Write-Host "PlatformIO no esta instalado en esta PC." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Este boton es solo para modificar el firmware."
    Write-Host "Para grabar el firmware ya compilado en la escuela usa:"
    Write-Host "  SUBIR_FIRMWARE.bat"
    Write-Host ""
    Write-Host "Para instalar PlatformIO en la PC de desarrollo:"
    Write-Host "  - Instala VS Code y la extension PlatformIO IDE, o"
    Write-Host "  - ejecuta: python -m pip install platformio"
    Write-Host ""
    exit 1
}

$configuredPort = ""
$configPath = Join-Path $root "pc\config.json"
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        if ($config.serial -and $config.serial.port) {
            $configuredPort = [string]$config.serial.port
        }
    } catch {
        $configuredPort = ""
    }
}

Write-Host ""
Write-Host "PlatformIO: $pio" -ForegroundColor Green
if ($configuredPort) {
    Write-Host "Puerto configurado: $configuredPort" -ForegroundColor Green
} else {
    Write-Host "Puerto: lo detecta PlatformIO automaticamente." -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "La primera compilacion descarga el core de ESP32 y ESP32Servo."
Write-Host "Necesita internet la primera vez en esta PC."
Write-Host ""

if ($CheckOnly) {
    Write-Host "CheckOnly: entorno encontrado; no se compila ni sube nada."
    exit 0
}

try {
    Set-Location $firmwareDir
    if ($configuredPort) {
        & $pio run -t upload --upload-port $configuredPort
    } else {
        & $pio run -t upload
    }
    $code = $LASTEXITCODE
} finally {
    Set-Location $root
}

if ($code -ne 0) {
    Write-Host ""
    Write-Host "ERROR al compilar o subir." -ForegroundColor Red
    Write-Host "Revisa el puerto COM, el driver y que la placa no este en uso." -ForegroundColor Yellow
    Write-Host "Si no entra en modo grabacion, mantene BOOT al conectar." -ForegroundColor Yellow
    exit $code
}

Write-Host ""
Write-Host "Firmware compilado y subido con PlatformIO." -ForegroundColor Green
Write-Host "Este binario nuevo no reemplaza automaticamente al precompilado del pendrive."
exit 0
