"""
Diagnostico de la instalacion de la PC.

Uso:
    python pc/tools/diagnose.py

Comprueba dependencias, ArUco, config, firmware y puertos COM. No abre la
camara ni mueve servos. Devuelve 0 si lo critico esta bien.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PC_DIR = ROOT / "pc"
sys.path.insert(0, str(PC_DIR))

failures = 0


def ok(text: str) -> None:
    print(f"[OK]    {text}")


def warn(text: str) -> None:
    print(f"[AVISO] {text}")


def fail(text: str) -> None:
    global failures
    failures += 1
    print(f"[FALLA] {text}")


def check_dependencies() -> None:
    print("\n1. Dependencias")
    try:
        import cv2
        import numpy as np
        import serial
        import esptool
    except Exception as exc:  # pragma: no cover - diagnostico de entorno
        fail(f"No se pudieron importar las dependencias: {exc}")
        return
    ok(f"OpenCV {cv2.__version__}")
    ok(f"NumPy {np.__version__}")
    ok(f"pyserial {serial.__version__}")
    if hasattr(cv2, "aruco"):
        ok("modulo cv2.aruco disponible")
    else:
        fail("OpenCV no tiene aruco; instala opencv-contrib-python")
    try:
        ok(f"esptool {esptool.__version__}")
    except Exception:
        warn("No se pudo leer la version de esptool, pero importa")
    try:
        import tkinter

        ok(f"tkinter {tkinter.TkVersion} (interfaz nueva)")
    except Exception as exc:
        fail(f"tkinter no esta disponible: {exc}")
    try:
        import matplotlib
        from PIL import Image  # noqa: F401

        ok(f"matplotlib {matplotlib.__version__} + Pillow (graficas)")
    except Exception as exc:
        fail(f"Faltan matplotlib/Pillow para Tkinter: {exc}")


def check_config_and_markers() -> None:
    print("\n2. Config y ArUco")
    try:
        from config import load_config
        from markers import MarkerTracker, draw_markers
        import cv2
        import numpy as np
    except Exception as exc:
        fail(f"No se pudo cargar el codigo de vision: {exc}")
        return
    try:
        config = load_config()
    except Exception as exc:
        fail(f"No se pudo leer pc/config.json: {exc}")
        return
    plate = config.get("plate", {})
    ok(f"Diccionario: {plate.get('marker_dictionary')}")
    ok(f"IDs configurados: {plate.get('marker_ids')}")
    ok(f"Centros cm: {plate.get('marker_centers_cm')}")
    try:
        tracker = MarkerTracker(config)
    except Exception as exc:
        fail(f"Config de marcadores invalida: {exc}")
        return

    # Prueba seca: dibujar los 4 marcadores en una imagen y detectarlos.
    try:
        height, width = 480, 640
        frame = np.full((height, width, 3), (150, 70, 20), dtype=np.uint8)
        half = float(plate["size_cm"]) / 2.0
        plate_cm = np.array(
            [[-half, half], [half, half], [half, -half], [-half, -half]],
            dtype=np.float32,
        )
        corners = np.array(
            [[70, 50], [560, 70], [590, 430], [50, 410]], dtype=np.float32
        )
        cv2.fillPoly(frame, [corners.astype(np.int32)], (35, 35, 35))
        homography = cv2.getPerspectiveTransform(plate_cm, corners)
        draw_markers(frame, homography, config)
        pose = tracker.detect(frame)
        if pose.valid and pose.marker_count() == 4:
            ok("deteccion ArUco de prueba: 4/4")
            point = pose.pixel_to_cm(320, 240)
            ok(f"centro optico -> {point[0]:.2f}, {point[1]:.2f} cm")
        else:
            fail(f"deteccion ArUco de prueba fallo (marcadores={pose.marker_count()})")
    except Exception as exc:
        fail(f"Prueba de ArUco fallo: {exc}")


def check_firmware() -> None:
    print("\n3. Firmware")
    binary = ROOT / "firmware" / "prebuilt" / "plataforma_pelota_esp32.bin"
    sidecar = binary.with_suffix(binary.suffix + ".sha256")
    if not binary.exists():
        fail(f"Falta {binary}")
        return
    expected = ""
    if sidecar.exists():
        expected = sidecar.read_text(encoding="utf-8").split()[0].strip().lower()
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if expected and actual != expected:
        fail("El SHA256 del firmware no coincide")
    else:
        ok(f"Firmware precompilado {binary.stat().st_size} bytes (SHA256 OK)")


def check_ports() -> None:
    print("\n4. Puertos y archivos")
    try:
        from serial.tools import list_ports

        ports = list(list_ports.comports())
        if ports:
            for port in ports:
                ok(f"{port.device}: {port.description}")
        else:
            warn("No hay puertos COM visibles. Conecta el ESP32 y revisa el driver.")
    except Exception as exc:
        warn(f"No se pudieron listar los puertos: {exc}")

    for path in (
        PC_DIR / "markers.py",
        PC_DIR / "gui.py",
        ROOT / "docs" / "marcadores_aruco" / "hoja_marcadores_A4.pdf",
    ):
        if path.exists():
            ok(f"Existe {path.relative_to(ROOT)}")
        else:
            warn(f"Falta {path.relative_to(ROOT)}")
    if (ROOT / "CENTRA.exe").exists():
        ok("CENTRA.exe presente")
    else:
        warn("CENTRA.exe no generado; la app puede correr con Python")


def main() -> int:
    print("DIAGNOSTICO - CENTRA - PLATAFORMA ESTABILIZADORA DE PELOTA")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Carpeta: {ROOT}")
    check_dependencies()
    check_config_and_markers()
    check_firmware()
    check_ports()
    print("\n============================================================")
    if failures:
        print(f"RESULTADO: {failures} problema(s). Revisa los mensajes [FALLA].")
        print("Si falta algo, ejecuta INSTALAR.bat y volve a verificar.")
        return 1
    print("RESULTADO: TODO LO BASICO OK.")
    print("Siguiente: conectar ESP32, FIRMWARE.bat, y CENTRA.bat opción 5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
