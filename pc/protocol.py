"""
Protocolo serie de texto entre la PC y el ESP32.

Formato general: una línea ASCII terminada en "\\n". Este módulo no abre el
puerto serie: solo arma y parsea líneas. Tanto el enlace real como el
FakeESP32 de la simulación usan estas mismas funciones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Telemetry:
    """Una línea T válida del ESP32."""

    ms: int
    x: float
    y: float
    err_x: float
    err_y: float
    tilt_x: float
    tilt_y: float
    servo_x: float
    servo_y: float
    state: int

    @property
    def error_magnitude(self) -> float:
        return math.hypot(self.err_x, self.err_y)


def parse_telemetry(line: str) -> Telemetry | None:
    """Devuelve Telemetry o None. Nunca lanza una excepción por una línea mala."""
    if not isinstance(line, str):
        return None
    try:
        parts = line.strip().split(",")
        if len(parts) != 11 or parts[0] != "T":
            return None

        ms = int(parts[1])
        values = [float(part) for part in parts[2:10]]
        state = int(parts[10])
        if ms < 0 or state not in (0, 1, 2, 3, 4):
            return None
        if any(not math.isfinite(value) for value in values):
            return None
        return Telemetry(ms, *values, state)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_hello(line: str) -> str | None:
    """Devuelve la versión si la línea es HELLO,<version>."""
    if not isinstance(line, str):
        return None
    text = line.strip()
    if not text.startswith("HELLO,"):
        return None
    version = text.split(",", 1)[1].strip()
    return version or None


def parse_host_command(line: str):
    """
    Parsea un comando PC -> ESP32 y devuelve (tipo, tupla_de_argumentos).

    Se usa en el FakeESP32 y en las pruebas. Devuelve None para cualquier
    línea inválida, truncada o desconocida. No lanza excepciones.
    """
    if not isinstance(line, str):
        return None
    text = line.strip("\r\n ")
    if not text:
        return None

    try:
        parts = [part.strip() for part in text.split(",")]
        command = parts[0]
        if command == "P" and len(parts) == 4:
            x, y = float(parts[1]), float(parts[2])
            found = int(parts[3])
            if not (math.isfinite(x) and math.isfinite(y)):
                return None
            if found not in (0, 1):
                return None
            return "P", (x, y, found)
        if command == "M" and len(parts) == 2:
            mode = int(parts[1])
            if mode not in (0, 1, 2):
                return None
            return "M", (mode,)
        if command == "A" and len(parts) == 3:
            tx, ty = float(parts[1]), float(parts[2])
            if not (math.isfinite(tx) and math.isfinite(ty)):
                return None
            return "A", (tx, ty)
        if command == "V" and len(parts) == 3:
            sx, sy = float(parts[1]), float(parts[2])
            if not (math.isfinite(sx) and math.isfinite(sy)):
                return None
            return "V", (sx, sy)
        if command == "G" and len(parts) == 5:
            axis = parts[1]
            if axis not in ("X", "Y", "B"):
                return None
            kp, ki, kd = float(parts[2]), float(parts[3]), float(parts[4])
            if not all(math.isfinite(v) for v in (kp, ki, kd)):
                return None
            return "G", (axis, kp, ki, kd)
        if command == "S" and len(parts) == 3:
            sx, sy = float(parts[1]), float(parts[2])
            if not (math.isfinite(sx) and math.isfinite(sy)):
                return None
            return "S", (sx, sy)
        if command == "C" and len(parts) == 3:
            ox, oy = float(parts[1]), float(parts[2])
            if not (math.isfinite(ox) and math.isfinite(oy)):
                return None
            return "C", (ox, oy)
        if command == "L" and len(parts) == 2:
            limit = float(parts[1])
            if not math.isfinite(limit):
                return None
            return "L", (limit,)
        if command == "W" and len(parts) == 1:
            return "W", ()
        if command == "H" and len(parts) == 1:
            return "H", ()
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def format_pose(x_cm: float, y_cm: float, found: bool) -> str:
    """Arma P con posición en cm y 2 decimales. El firmware limita el rango."""
    return f"P,{float(x_cm):.2f},{float(y_cm):.2f},{1 if found else 0}"


def format_mode(mode: int) -> str:
    if mode not in (0, 1, 2):
        raise ValueError("El modo debe ser 0, 1 o 2")
    return f"M,{mode}"


def format_tilt(tilt_x: float, tilt_y: float) -> str:
    return f"A,{float(tilt_x):.2f},{float(tilt_y):.2f}"


def format_raw_servo(servo_x: float, servo_y: float) -> str:
    return f"V,{float(servo_x):.2f},{float(servo_y):.2f}"


def format_gains(axis: str, kp: float, ki: float, kd: float) -> str:
    axis = axis.upper()
    if axis not in ("X", "Y", "B"):
        raise ValueError("El eje debe ser X, Y o B")
    return f"G,{axis},{float(kp):.3f},{float(ki):.3f},{float(kd):.3f}"


def format_setpoint(x_cm: float, y_cm: float) -> str:
    """Setpoint en cm. El firmware lo limita al tamaño de la placa."""
    return f"S,{float(x_cm):.2f},{float(y_cm):.2f}"


def format_offsets(offset_x: float, offset_y: float) -> str:
    return f"C,{float(offset_x):.2f},{float(offset_y):.2f}"


def format_tilt_limit(limit_deg: float) -> str:
    return f"L,{float(limit_deg):.2f}"


def format_telemetry(
    ms: int,
    x: float,
    y: float,
    err_x: float,
    err_y: float,
    tilt_x: float,
    tilt_y: float,
    servo_x: float,
    servo_y: float,
    state: int,
) -> str:
    """Formato de telemetría compartido por el firmware (mismo orden de campos)."""
    return (
        f"T,{int(ms)},{x:.3f},{y:.3f},{err_x:.3f},{err_y:.3f},"
        f"{tilt_x:.3f},{tilt_y:.3f},{servo_x:.2f},{servo_y:.2f},"
        f"{int(state)}"
    )
