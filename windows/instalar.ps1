# Instalador de Plataforma Pelota para Windows.
# Se ejecuta desde INSTALAR.bat. No requiere permisos de administrador.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$pcDir = Join-Path $root "pc"
$venvDir = Join-Path $pcDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Text)
    Write-Host "    OK: $Text" -ForegroundColor Green
}

function Get-PythonInfo {
    param(
        [string]$Exe,
        [string[]]$Prefix
    )
    $exePath = $null
    $command = Get-Command $Exe -ErrorAction SilentlyContinue
    if ($command) {
        $exePath = $command.Source
    } elseif (Test-Path $Exe) {
        $exePath = (Resolve-Path $Exe).Path
    } else {
        return $null
    }
    $probe = "import sys,struct; print(str(sys.version_info[0])+'.'+str(sys.version_info[1])+'|'+str(struct.calcsize('P')*8))"
    try {
        $output = & $exePath @Prefix -c $probe 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }
    $text = [string]($output | Select-Object -First 1)
    $parts = $text.Trim().Split("|")
    if ($parts.Count -ne 2) { return $null }
    try {
        return [PSCustomObject]@{
            Exe = $exePath
            Prefix = $Prefix
            Version = [version]$parts[0]
            Bits = [int]$parts[1]
        }
    } catch {
        return $null
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "  PLATAFORMA ESTABILIZADORA DE PELOTA - INSTALACION EN WINDOWS" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "  No hace falta ser administrador. No se necesita GPU."

function Find-PythonCandidate {
    $localPython312 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    $candidates = @(
        @{ Exe = "py"; Prefix = @("-3.12") },
        @{ Exe = $localPython312; Prefix = @() },
        @{ Exe = "py"; Prefix = @("-3") },
        @{ Exe = "python"; Prefix = @() },
        @{ Exe = "python3"; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $info = Get-PythonInfo -Exe $candidate.Exe -Prefix $candidate.Prefix
        if ($null -ne $info -and $info.Version -ge [version]"3.10") {
            return $info
        }
    }
    return $null
}

Write-Step "Buscando Python 3.10 o superior"
$python = Find-PythonCandidate

if ($null -eq $python) {
    Write-Host "    No se encontro Python 3.10 o superior." -ForegroundColor Yellow
    $installersDir = Join-Path $root "paquete\instaladores"
    $installer = $null
    if (Test-Path $installersDir) {
        $installer = Get-ChildItem $installersDir -Filter "python-*-amd64.exe" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            Select-Object -First 1
    }
    if ($null -ne $installer) {
        Write-Host ""
        Write-Host "    Hay un instalador de Python incluido en el paquete:" -ForegroundColor Cyan
        Write-Host "      $($installer.FullName)"
        Write-Host ""
        Write-Host "    Marca 'Add python.exe to PATH' en el instalador."
        Write-Host ""
        try {
            $answer = Read-Host "    Abrir el instalador de Python ahora? (S/N)"
        } catch {
            $answer = "N"
        }
        if ($answer -match "^(s|si|y|yes)$") {
            Write-Host "    Abriendo instalador. Cuando termine, la instalacion continua..." -ForegroundColor Cyan
            Start-Process -FilePath $installer.FullName -Wait
            Write-Step "Buscando Python despues de la instalacion"
            $python = Find-PythonCandidate
        } else {
            Write-Host "    Ejecuta ese instalador y despues volve a abrir INSTALAR.bat."
            exit 1
        }
    } else {
        Write-Host "    Instala Python 3.12 de 64 bits desde:" -ForegroundColor Cyan
        Write-Host "      https://www.python.org/downloads/windows/"
        Write-Host "    Marca 'Add python.exe to PATH' y volve a ejecutar INSTALAR.bat."
        exit 1
    }
    if ($null -eq $python) {
        Write-Host "    Todavia no se detecta Python." -ForegroundColor Yellow
        Write-Host "    Cierra esta ventana, abre una nueva y ejecuta INSTALAR.bat." -ForegroundColor Yellow
        exit 1
    }
}

Write-Ok "Python $($python.Version) de $($python.Bits) bits en $($python.Exe)"
if ($python.Bits -ne 64) {
    Write-Host "    ERROR: se necesita Python de 64 bits para OpenCV." -ForegroundColor Red
    exit 1
}

Write-Step "Creando el entorno virtual pc\.venv"
$venvUsable = $false
if (Test-Path $venvPython) {
    try {
        & $venvPython -c "import sys; print(sys.prefix)" *> $null
        if ($LASTEXITCODE -eq 0) { $venvUsable = $true }
    } catch {
        $venvUsable = $false
    }
}
if (-not $venvUsable) {
    if (Test-Path $venvDir) {
        Write-Host "    El entorno virtual existente no funciona en esta PC; se recrea..." -ForegroundColor Yellow
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }
    & $python.Exe @($python.Prefix) -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Write-Host "    ERROR: no se pudo crear el entorno virtual." -ForegroundColor Red
        Write-Host "    Proba ejecutar: $($python.Exe) -m venv pc\.venv"
        exit 1
    }
    Write-Ok "Entorno virtual creado"
} else {
    Write-Ok "El entorno virtual existente funciona; se reutiliza"
}

$requirements = Join-Path $pcDir "requirements.txt"
$flashRequirements = Join-Path $pcDir "tools\requirements-flash.txt"
$wheelsDir = Join-Path $root "paquete\wheels"
$hasWheels = $false
if (Test-Path $wheelsDir) {
    $wheelFiles = @(Get-ChildItem $wheelsDir -Filter "*.whl" -ErrorAction SilentlyContinue)
    if ($wheelFiles.Count -gt 0) { $hasWheels = $true }
}

Write-Step "Instalando dependencias de la PC"
if ($hasWheels) {
    Write-Host "    Modo OFFLINE: usando las ruedas de paquete\wheels" -ForegroundColor Green
    $envFile = Join-Path $root "paquete\entorno.txt"
    if (Test-Path $envFile) {
        Write-Host "    Entorno preparado:" -ForegroundColor DarkGray
        Get-Content $envFile | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
    }
    if ($python.Version.Major -ne 3 -or $python.Version.Minor -ne 12) {
        Write-Host "    AVISO: el paquete offline suele estar preparado para Python 3.12 x64." -ForegroundColor Yellow
        Write-Host "    Si falla, instala Python 3.12 del paquete o prepara el pendrive de nuevo." -ForegroundColor Yellow
    }
    $installArgs = @(
        "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
        "--no-index", "--find-links", $wheelsDir,
        "-r", $requirements, "-r", $flashRequirements
    )
    & $venvPython @installArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "    ERROR: fallo la instalacion offline." -ForegroundColor Red
        Write-Host "    Causas posibles: version de Python distinta, archivo faltante" -ForegroundColor Yellow
        Write-Host "    o paquete preparado en otra arquitectura." -ForegroundColor Yellow
        Write-Host "    En la PC con internet ejecuta PREPARAR_PENDRIVE.bat y volve a copiar." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "    No hay paquete offline; se descarga desde internet." -ForegroundColor Cyan
    $installArgs = @(
        "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
        "-r", $requirements, "-r", $flashRequirements
    )
    & $venvPython @installArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "    ERROR: no se pudieron instalar las dependencias." -ForegroundColor Red
        Write-Host "    Revisa la conexion a internet o ejecuta PREPARAR_PENDRIVE.bat" -ForegroundColor Yellow
        Write-Host "    en una PC con internet." -ForegroundColor Yellow
        exit 1
    }
}
Write-Ok "OpenCV, NumPy, pyserial y esptool instalados"

Write-Step "Verificando la instalacion"
$check = "import cv2, numpy, serial, esptool; assert hasattr(cv2, 'aruco'), 'OpenCV sin modulo aruco'; print('OpenCV', cv2.__version__); print('ArUco OK'); print('NumPy', numpy.__version__); print('pyserial', serial.__version__)"
& $venvPython -c $check
if ($LASTEXITCODE -ne 0) {
    Write-Host "    ERROR: alguna dependencia no se puede importar o falta ArUco." -ForegroundColor Red
    Write-Host "    Ejecuta PREPARAR_PENDRIVE.bat de nuevo para regenerar los wheels." -ForegroundColor Yellow
    exit 1
}

$firmware = Join-Path $root "firmware\prebuilt\plataforma_pelota_esp32.bin"
$firmwareSha = $firmware + ".sha256"
if (Test-Path $firmware) {
    Write-Ok "Firmware precompilado presente ($((Get-Item $firmware).Length) bytes)"
    if (Test-Path $firmwareSha) {
        $expected = ((Get-Content $firmwareSha -TotalCount 1) -split "\s+")[0].ToLower()
        $actual = (Get-FileHash $firmware -Algorithm SHA256).Hash.ToLower()
        if ($expected -eq $actual) {
            Write-Ok "SHA256 del firmware correcto"
        } else {
            Write-Host "    AVISO: el SHA256 no coincide; volve a copiar el firmware." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "    AVISO: no se encontro el firmware precompilado." -ForegroundColor Yellow
    Write-Host "    Igual podes compilarlo con COMPILAR_Y_SUBIR_CON_PLATFORMIO.bat." -ForegroundColor Yellow
}

Write-Step "Creando acceso directo en el escritorio"
try {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "Plataforma Pelota.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $root "INICIAR.bat"
    $shortcut.WorkingDirectory = $root
    $shortcut.WindowStyle = 1
    $shortcut.Description = "Plataforma estabilizadora de pelota"
    $shortcut.Save()
    Write-Ok "Acceso directo: $shortcutPath"
} catch {
    Write-Host "    No se pudo crear el acceso directo (no es grave)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  INSTALACION TERMINADA" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Siguientes pasos:" -ForegroundColor White
Write-Host "  1. Conecta el ESP32 por USB y ejecuta SUBIR_FIRMWARE.bat" -ForegroundColor Cyan
Write-Host "     (solo la primera vez o cuando actualices el firmware)."
Write-Host "  2. Ejecuta ELEGIR_DISPOSITIVOS.bat para elegir camara y COM."
Write-Host "  3. Ejecuta INICIAR.bat."
Write-Host ""
Write-Host "  Sin hardware podes probar ya con PROBAR_SIN_HARDWARE.bat."
Write-Host ""
Write-Host "  Lee GUIA_PENDRIVE.md para llevar todo a la escuela." -ForegroundColor DarkGray
Write-Host ""

exit 0
