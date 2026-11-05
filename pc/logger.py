"""Registro CSV de la telemetría del ESP32."""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path


class TelemetryLogger:
    """Escribe una fila por cada T nueva, sin bloquear el hilo de la GUI."""

    FIELD_NAMES = (
        "tiempo_s",
        "hora",
        "esp_ms",
        "x",
        "y",
        "err_x",
        "err_y",
        "tilt_x",
        "tilt_y",
        "servo_x",
        "servo_y",
        "estado",
    )

    def __init__(self, directory: str | Path, enabled: bool = True):
        self.enabled = bool(enabled)
        self.path: Path | None = None
        self._file = None
        self._writer = None
        self._rows = 0
        self.started_at = time.time()

        if not self.enabled:
            return

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = directory / f"telemetria_{stamp}.csv"
        self._file = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.FIELD_NAMES)
        self._file.flush()

    def log(self, telemetry) -> None:
        if not self.enabled or self._writer is None:
            return
        now = datetime.now()
        self._writer.writerow(
            [
                f"{time.time() - self.started_at:.3f}",
                now.isoformat(timespec="milliseconds"),
                telemetry.ms,
                f"{telemetry.x:.4f}",
                f"{telemetry.y:.4f}",
                f"{telemetry.err_x:.4f}",
                f"{telemetry.err_y:.4f}",
                f"{telemetry.tilt_x:.3f}",
                f"{telemetry.tilt_y:.3f}",
                f"{telemetry.servo_x:.2f}",
                f"{telemetry.servo_y:.2f}",
                telemetry.state,
            ]
        )
        self._rows += 1
        # Un flush por fila (25 Hz) permite ver el CSV en vivo y no perder
        # datos si el programa se cierra de forma inesperada.
        self._file.flush()

    @property
    def rows(self) -> int:
        return self._rows

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            finally:
                self._file = None
                self._writer = None
