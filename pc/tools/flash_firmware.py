"""
Flashea el firmware precompilado en un ESP32 DevKit usando esptool.

Uso normal (lo llama FIRMWARE.bat, opción 1):
    python pc/tools/flash_firmware.py

Opciones utiles:
    --list                 listar puertos y salir
    --port COM5            no preguntar el puerto
    --bin ruta.bin         usar otro binario
    --dry-run              mostrar el comando sin tocar el ESP32

Este archivo no importa OpenCV para poder usarse aunque falle la parte de
vision. El binario precompilado ya incluye bootloader + tablas + aplicacion y
se escribe en la direccion 0x0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    from serial.tools import list_ports
except ImportError:
    print("Falta pyserial. Ejecuta INSTALAR.bat primero.")
    raise SystemExit(2)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PC_DIR = PROJECT_ROOT / "pc"
CONFIG_PATH = PC_DIR / "config.json"
DEFAULT_FIRMWARE = (
    PROJECT_ROOT / "firmware" / "prebuilt" / "plataforma_pelota_esp32.bin"
)
FLASH_ADDRESS = "0x0"


def read_configured_port() -> str:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return str(data.get("serial", {}).get("port", "") or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def get_ports():
    try:
        return sorted(list_ports.comports(), key=lambda item: item.device)
    except Exception:
        return []


def print_ports(ports) -> None:
    configured = read_configured_port()
    if not ports:
        print("No se detectaron puertos COM.")
        print("Revisa el cable USB, el driver CH340/CP210x y que otro programa")
        print("(Arduino IDE, monitor serie) no este usando el puerto.")
        return
    print("Puertos detectados:")
    for index, info in enumerate(ports, start=1):
        suffix = "  <-- configurado" if info.device == configured else ""
        print(f"  {index}. {info.device}  {info.description}{suffix}")


def ask_port(ports, allow_default=True) -> str:
    configured = read_configured_port()
    default = ""
    if allow_default and configured:
        default = configured
    elif allow_default and len(ports) == 1:
        default = ports[0].device

    print_ports(ports)
    while True:
        hint = f" [{default}]" if default else ""
        raw = input(
            f"Elegi un numero, escribi el puerto (ej. COM5) o Enter{hint}: "
        ).strip()
        if not raw:
            if default:
                return default
            print("Escribi un puerto o elegi un numero de la lista.")
            continue
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(ports):
                return ports[index - 1].device
            print("Ese numero no esta en la lista.")
            continue
        return raw


def verify_firmware(path: Path) -> bool:
    if not path.is_file():
        print(f"No existe el firmware: {path}")
        return False
    size = path.stat().st_size
    if size < 100_000:
        print(f"El firmware parece incompleto ({size} bytes).")
        return False

    sha_file = path.with_suffix(path.suffix + ".sha256")
    if sha_file.is_file():
        expected = sha_file.read_text(encoding="utf-8").split()[0].strip().lower()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected and expected != actual:
            print("El SHA256 del firmware no coincide. Volvé a copiar")
            print("firmware/prebuilt/plataforma_pelota_esp32.bin desde el proyecto.")
            return False
    return True


def build_command(port: str, baud: int, firmware: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        "esp32",
        "--port",
        port,
        "--baud",
        str(baud),
        "write-flash",
        "--flash-mode",
        "dio",
        "--flash-freq",
        "40m",
        "--flash-size",
        "detect",
        FLASH_ADDRESS,
        str(firmware),
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Flashear el firmware precompilado de Plataforma Pelota"
    )
    parser.add_argument("--port", "-p", default=None, help="puerto COM, ej. COM5")
    parser.add_argument(
        "--bin",
        "-b",
        default=str(DEFAULT_FIRMWARE),
        help="binario fusionado a flashear",
    )
    parser.add_argument("--baud", type=int, default=460800, help="velocidad de flasheo")
    parser.add_argument("--list", action="store_true", help="solo listar puertos")
    parser.add_argument("--dry-run", action="store_true", help="no tocar el ESP32")
    parser.add_argument("--yes", "-y", action="store_true", help="no pedir confirmacion")
    args = parser.parse_args(argv)

    ports = get_ports()
    if args.list:
        print_ports(ports)
        return 0

    firmware = Path(args.bin).expanduser().resolve()
    if not verify_firmware(firmware):
        return 2
    sha = hashlib.sha256(firmware.read_bytes()).hexdigest()

    print("=" * 66)
    print("  GRABAR FIRMWARE EN EL ESP32")
    print("=" * 66)
    print(f"Firmware: {firmware}")
    print(f"Tamano:   {firmware.stat().st_size} bytes")
    print(f"SHA256:   {sha[:32]}...")
    print()
    print("Cable USB conectado al ESP32. Cerra Arduino IDE y el monitor serie.")
    print("Si la placa no entra sola en modo grabacion, mantene presionado BOOT")
    print("al comenzar y soltalo cuando aparezca Connecting...")
    print()

    if args.port:
        port = str(args.port).strip()
    else:
        try:
            port = ask_port(ports)
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return 1
    if not port:
        print("No hay puerto seleccionado.")
        return 2

    if not args.yes and not args.dry_run:
        try:
            answer = input(f"Escribir el firmware en {port}? (S/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado; no se toco el ESP32.")
            return 1

    command = build_command(port, args.baud, firmware)
    print("\nComando:")
    print("  " + " ".join(command))
    if args.dry_run:
        print("\nDry-run: no se abrio el puerto ni se grabo nada.")
        return 0

    print("\nGrabando... (no desconectes el USB)")
    try:
        code = subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        print("No se encontro esptool. Ejecuta INSTALAR.bat.")
        return 3
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        return 1

    print()
    if code == 0:
        print("=" * 66)
        print("  FIRMWARE GRABADO CORRECTAMENTE")
        print("=" * 66)
        print("Desconecta y reconecta el ESP32. Despues ejecuta CENTRA.bat.")
        print("Si la app no lo encuentra, usa CENTRA.bat, opción 5.")
        return 0

    print("=" * 66)
    print(f"  ERROR DE ESPTOOL (codigo {code})")
    print("=" * 66)
    print("Revisa:")
    print("  1. Que el puerto COM sea el del ESP32.")
    print("  2. Driver CH340 o CP210x instalado.")
    print("  3. Cable USB de datos, no solo de carga.")
    print("  4. Cerrar Arduino IDE / monitor serie / otras apps que usen el COM.")
    print("  5. Probar otro puerto USB o mantener BOOT durante la conexion.")
    print("  6. Si el puerto esta ocupado, desconecta y reconecta.")
    return code or 1


if __name__ == "__main__":
    sys.exit(main())
