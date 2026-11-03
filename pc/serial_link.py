"""
Enlace serie con el ESP32.

- Un solo hilo de fondo se encarga de detectar el puerto, conectar, leer,
  escribir y reconectar. La GUI nunca se bloquea esperando al puerto.
- La detección automática abre cada COM y manda H; el puerto que responde
  HELLO,<version> es el elegido.
- Al reconectar se reenvían el modo y las ganancias (además del setpoint y
  los offsets, para no perder la configuración).
"""

from __future__ import annotations

import queue
import threading
import time
from collections import OrderedDict

import serial
from protocol import parse_hello, parse_telemetry
from serial.tools import list_ports

# TODO-HW: probar con el ESP32 real, distintos cables USB y reconexión.
DETECTION_WINDOW_S = 1.8
HELLO_RETRY_S = 0.35


class SerialLink:
    def __init__(self, config: dict, port_override: str | None = None):
        serial_config = config.get("serial", {})
        configured_port = (
            port_override
            if port_override is not None
            else str(serial_config.get("port", "") or "")
        )
        self._configured_port = configured_port.strip()
        self._auto_detect = bool(serial_config.get("auto_detect", True))
        self._baud = int(serial_config.get("baud", 115200))
        self._reconnect_delay_s = float(
            serial_config.get("reconnect_delay_s", 1.0)
        )

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial = None
        self._lock = threading.Lock()
        self._tx_queue: queue.Queue[str] = queue.Queue(maxsize=512)
        self._latest = None
        self._telemetry_count = 0
        self._connected = False
        self._port_description = self._configured_port or "Buscando..."
        self._hello_version = ""
        self._last_error = ""
        self._tx_dropped = 0

        # Para reenviar al reconectar. Las claves se guardan sin duplicados.
        self._stored_commands: "OrderedDict[str, str]" = OrderedDict()

    # ------------------------------------------------------------ interfaz ---
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="SerialLink", daemon=True
        )
        self._thread.start()

    def close(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        serial_port = self._serial
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def send(self, line: str) -> None:
        """Encola una línea sin bloquear jamás al llamador."""
        if not isinstance(line, str):
            return
        line = line.strip()
        if not line:
            return

        self._remember_command(line)

        if not self.connected:
            # Mientras no hay enlace no tiene sentido acumular P viejas.
            # M/G/S/C sí quedan guardadas para reenviarlas al conectar.
            return

        try:
            self._tx_queue.put_nowait(line)
        except queue.Full:
            self._tx_dropped += 1

    def send_pose(self, x: float, y: float, found: bool) -> None:
        from protocol import format_pose

        self.send(format_pose(x, y, found))

    def latest_telemetry(self):
        with self._lock:
            return self._latest

    def pending_tx(self) -> int:
        return self._tx_queue.qsize()

    # ------------------------------------------------------------ propiedad ---
    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def port_description(self) -> str:
        with self._lock:
            return self._port_description

    @property
    def hello_version(self) -> str:
        with self._lock:
            return self._hello_version

    @property
    def last_error(self) -> str:
        with self._lock:
            return self._last_error

    @property
    def telemetry_count(self) -> int:
        with self._lock:
            return self._telemetry_count

    @property
    def tx_dropped(self) -> int:
        return self._tx_dropped

    # ----------------------------------------------------------- internos ---
    def _remember_command(self, line: str) -> None:
        kind = line.split(",", 1)[0].upper()
        if kind not in ("M", "G", "S", "C"):
            return
        with self._lock:
            if kind == "M":
                self._stored_commands["M"] = line
            elif kind == "G":
                parts = line.split(",")
                axis = parts[1].upper() if len(parts) > 1 else "B"
                self._stored_commands[f"G{axis}"] = line
            else:
                self._stored_commands[kind] = line

    def _set_error(self, text: str) -> None:
        with self._lock:
            self._last_error = text

    def _set_connected(self, connected: bool, description: str = "") -> None:
        with self._lock:
            self._connected = connected
            if description:
                self._port_description = description

    def _run(self) -> None:
        while not self._stop_event.is_set():
            serial_port = None
            try:
                serial_port, description, version = self._find_and_connect()
                if serial_port is None:
                    if self._stop_event.wait(self._reconnect_delay_s):
                        break
                    continue

                with self._lock:
                    self._hello_version = version
                    self._last_error = ""
                self._set_connected(True, description)
                print(f"[serial] Conectado a {description} (firmware {version})")
                self._resend_stored_commands(serial_port)
                self._io_loop(serial_port)
            except Exception as exc:  # el enlace nunca debe tumbar la GUI
                message = str(exc).strip() or exc.__class__.__name__
                self._set_error(message)
                print(f"[serial] Error: {message}")
            finally:
                self._set_connected(False)
                self._drain_tx_queue()
                if serial_port is not None:
                    try:
                        serial_port.close()
                    except Exception:
                        pass
                    self._serial = None
                if not self._stop_event.is_set():
                    self._stop_event.wait(self._reconnect_delay_s)

    def _candidate_ports(self) -> list[tuple[str, str]]:
        if self._configured_port:
            return [(self._configured_port, self._configured_port)]

        if not self._auto_detect:
            self._set_error("No hay puerto configurado")
            return []

        candidates = []
        for info in list_ports.comports():
            device = getattr(info, "device", "")
            if not device:
                continue
            description = getattr(info, "description", "") or device
            candidates.append((device, f"{device} ({description})"))
        return candidates

    def _find_and_connect(self):
        candidates = self._candidate_ports()
        if not candidates:
            self._set_error("No se encontraron puertos COM")
            return None, "", ""

        for device, description in candidates:
            if self._stop_event.is_set():
                return None, "", ""
            serial_port = None
            try:
                serial_port = serial.Serial(
                    port=device,
                    baudrate=self._baud,
                    timeout=0.02,
                    write_timeout=0.5,
                    rtscts=False,
                    dsrdtr=False,
                )
                self._serial = serial_port
                # No dejar DTR/RTS forzando un reset en los ESP32 DevKit.
                try:
                    serial_port.dtr = False
                    serial_port.rts = False
                except Exception:
                    pass
                serial_port.reset_input_buffer()
                version = self._wait_for_hello(serial_port)
                if version:
                    self._set_connected(True, description)
                    return serial_port, description, version
                serial_port.close()
            except (OSError, serial.SerialException) as exc:
                if serial_port is not None:
                    try:
                        serial_port.close()
                    except Exception:
                        pass
                self._set_error(f"{device}: {exc}")
        return None, "", ""

    def _wait_for_hello(self, serial_port) -> str:
        deadline = time.monotonic() + DETECTION_WINDOW_S
        next_hello = 0.0
        buffer = b""
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_hello:
                serial_port.write(b"H\n")
                next_hello = now + HELLO_RETRY_S

            try:
                waiting = serial_port.in_waiting
                data = serial_port.read(waiting if waiting > 0 else 1)
            except (OSError, serial.SerialException):
                return ""
            if not data:
                continue
            buffer += data
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                line = raw.decode("ascii", errors="ignore").strip()
                if not line:
                    continue
                version = parse_hello(line)
                if version:
                    return version
                telemetry = parse_telemetry(line)
                if telemetry is not None:
                    with self._lock:
                        self._latest = telemetry
                        self._telemetry_count += 1
        return ""

    def _resend_stored_commands(self, serial_port) -> None:
        with self._lock:
            commands = list(self._stored_commands.values())
        for line in commands:
            serial_port.write((line + "\n").encode("ascii", errors="ignore"))
            time.sleep(0.01)

    def _drain_tx_queue(self) -> None:
        while True:
            try:
                self._tx_queue.get_nowait()
            except queue.Empty:
                break

    def _io_loop(self, serial_port) -> None:
        buffer = b""
        while not self._stop_event.is_set():
            # Primero vaciar la cola para mantener baja la latencia de control.
            for _ in range(80):
                try:
                    line = self._tx_queue.get_nowait()
                except queue.Empty:
                    break
                serial_port.write((line + "\n").encode("ascii", errors="ignore"))

            try:
                waiting = serial_port.in_waiting
                data = serial_port.read(waiting if waiting > 0 else 1)
            except (OSError, serial.SerialException) as exc:
                raise serial.SerialException(f"Lectura serie: {exc}") from exc
            if not data:
                continue

            buffer += data
            if len(buffer) > 4096:
                buffer = buffer[-2048:]

            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                line = raw.decode("ascii", errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("HELLO,"):
                    version = parse_hello(line)
                    if version:
                        with self._lock:
                            self._hello_version = version
                    continue
                if line.startswith("ERR,"):
                    self._set_error(line[4:])
                    continue
                telemetry = parse_telemetry(line)
                if telemetry is not None:
                    with self._lock:
                        self._latest = telemetry
                        self._telemetry_count += 1
