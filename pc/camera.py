"""
Hilo de captura de cámara con buffer de un solo cuadro.

Acepta un índice de OpenCV (por ejemplo 0) o una URL de stream (DroidCam,
Iriun, IP Webcam, etc.). El hilo lee todo el tiempo para descartar cuadros
viejos y que la GUI nunca se quede esperando a la cámara.
"""

from __future__ import annotations

import platform
import threading
import time
from collections import deque
from typing import NamedTuple

import cv2


class FramePacket(NamedTuple):
    frame: object
    timestamp: float
    index: int


def _coerce_source(source):
    if isinstance(source, str):
        text = source.strip()
        if text.isdigit():
            return int(text)
        return text
    return source


def _fourcc_code(text: str) -> int:
    text = (text or "").strip()
    if len(text) != 4:
        return 0
    return cv2.VideoWriter_fourcc(*text)


class CameraThread:
    """Captura en un hilo y publica únicamente el último cuadro."""

    def __init__(self, config: dict, source_override=None):
        camera_config = config.get("camera", {})
        self.source = _coerce_source(
            source_override if source_override is not None else camera_config.get("source", 0)
        )
        self.width = int(camera_config.get("width", 640))
        self.height = int(camera_config.get("height", 480))
        self.requested_fps = float(camera_config.get("fps", 60))
        self.fourcc = str(camera_config.get("fourcc", "MJPG"))
        self.backend_name = str(camera_config.get("backend", "dshow")).lower()
        self.reconnect_delay_s = float(camera_config.get("reconnect_delay_s", 1.0))

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture = None
        self._lock = threading.Lock()
        self._latest: FramePacket | None = None
        self._frame_index = 0
        self._read_times: deque[float] = deque(maxlen=40)
        self._measured_fps = 0.0
        self._status = "Cámara sin iniciar"
        self._actual_size = (0, 0)
        self._source_is_url = isinstance(self.source, str)

    # -------------------------------------------------------------- ciclo ---
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="CameraThread", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            capture = self._open_capture()
            if capture is None:
                self._set_status("No se pudo abrir la cámara")
                if self._stop_event.wait(self.reconnect_delay_s):
                    break
                continue

            self._capture = capture
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or self.width)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or self.height)
            self._actual_size = (width, height)
            self._set_status(f"Cámara {width}x{height}")

            consecutive_errors = 0
            while not self._stop_event.is_set():
                try:
                    ok, frame = capture.read()
                except cv2.error:
                    self._set_status("La cámara generó un error de lectura")
                    break
                if not ok or frame is None:
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        self._set_status("La cámara dejó de entregar cuadros")
                        break
                    self._stop_event.wait(0.05)
                    continue
                consecutive_errors = 0
                now = time.perf_counter()
                with self._lock:
                    self._frame_index += 1
                    self._latest = FramePacket(frame, now, self._frame_index)
                    self._read_times.append(now)
                    self._update_fps_locked()
                self._set_status(
                    f"Cámara {frame.shape[1]}x{frame.shape[0]} "
                    f"{self._measured_fps:.1f} fps"
                )

            capture.release()
            self._capture = None
            if not self._stop_event.is_set():
                self._stop_event.wait(self.reconnect_delay_s)

    def _open_capture(self):
        # TODO-HW: verificar con la cámara real del celular y el backend elegido.
        if self._source_is_url:
            backends = [cv2.CAP_FFMPEG, cv2.CAP_ANY]
        else:
            use_dshow = (
                self.backend_name == "dshow"
                and platform.system().lower().startswith("win")
            )
            backends = ([cv2.CAP_DSHOW] if use_dshow else []) + [cv2.CAP_ANY]

        attempted = set()
        for backend in backends:
            if backend in attempted:
                continue
            attempted.add(backend)
            try:
                capture = cv2.VideoCapture(self.source, backend)
            except cv2.error:
                capture = cv2.VideoCapture(self.source)
            if not capture.isOpened():
                capture.release()
                continue

            # Cuanto antes se piden las propiedades, mejor negocia el driver.
            code = _fourcc_code(self.fourcc)
            if code:
                capture.set(cv2.CAP_PROP_FOURCC, code)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            capture.set(cv2.CAP_PROP_FPS, self.requested_fps)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            ok, _ = capture.read()
            if ok:
                print(
                    f"[camara] Fuente {self.source!r}, "
                    f"{int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                    f"{int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
                    f"@{capture.get(cv2.CAP_PROP_FPS):.1f} fps solicitados"
                )
                return capture
            capture.release()
        return None

    def _update_fps_locked(self) -> None:
        if len(self._read_times) < 2:
            self._measured_fps = 0.0
            return
        elapsed = self._read_times[-1] - self._read_times[0]
        if elapsed > 0:
            self._measured_fps = (len(self._read_times) - 1) / elapsed

    # ------------------------------------------------------------- lectura ---
    def get_latest(self) -> FramePacket | None:
        with self._lock:
            return self._latest

    @property
    def fps(self) -> float:
        with self._lock:
            return self._measured_fps

    @property
    def status_text(self) -> str:
        with self._lock:
            return self._status

    @property
    def actual_size(self) -> tuple[int, int]:
        with self._lock:
            return self._actual_size

    def _set_status(self, text: str) -> None:
        with self._lock:
            self._status = text

    def stop(self) -> None:
        self._stop_event.set()
        capture = self._capture
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
