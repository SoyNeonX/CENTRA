"""
Interfaz de OpenCV.

Muestra el video, la ROI, la pelota, el setpoint, el estado y los fps. También
maneja las teclas, el mouse y las trackbars del PID. La comunicación con el
ESP32 siempre se hace a través del enlace no bloqueante.
"""

from __future__ import annotations

import time
import unicodedata
from pathlib import Path

import cv2
import numpy as np
from calibration import (
    AxisAssistant,
    calibrate_hsv,
    select_roi,
    servo_center_calibration,
)
from config import save_config
from devices import setup_devices
from protocol import (
    format_gains,
    format_mode,
    format_setpoint,
    format_tilt,
)
from vision import (
    build_roi_mask,
    corners_to_pixels,
    denormalize_point,
    normalize_point,
    pixels_to_normalized_corners,
)

STATE_NAMES = {
    0: "APAGADO",
    1: "MANUAL",
    2: "BUSCANDO",
    3: "ESTABILIZANDO",
    4: "PELOTA PERDIDA",
}
MODE_NAMES = {0: "APAGADO", 1: "MANUAL", 2: "AUTOMATICO"}

# Códigos que devuelve waitKeyEx para las flechas en Windows y Linux.
ARROW_KEYS = {
    2424832: "left",
    2555904: "right",
    2490368: "up",
    2621440: "down",
    65361: "left",
    65362: "up",
    65363: "right",
    65364: "down",
}

# Para los textos dibujados con Hershey, que no soporta acentos.
_ASCII_FIXES = str.maketrans(
    {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "ñ": "n",
        "Ñ": "N",
        "°": " deg ",
        "±": "+/-",
        "→": "->",
        "←": "<-",
        "↑": "arriba",
        "↓": "abajo",
    }
)


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text).translate(_ASCII_FIXES)).encode(
        "ascii", "ignore"
    ).decode("ascii")


class BallPlateGUI:
    def __init__(
        self,
        config: dict,
        link,
        config_path: str | Path,
        initial_mode: int = 0,
        simulation_mode: bool = False,
    ):
        self.config = config
        self.link = link
        self.config_path = Path(config_path)
        self.mode = int(initial_mode) if initial_mode in (0, 1, 2) else 0
        self.simulation_mode = bool(simulation_mode)
        self.running = True
        self.restart_requested = False

        gui_config = config.get("gui", {})
        self.window = str(gui_config.get("window_name", "Ball and plate"))
        self._window_created = False

        self.setpoint_x = float(config["control"].get("setpoint_x", 0.0))
        self.setpoint_y = float(config["control"].get("setpoint_y", 0.0))
        self.manual_step = float(config["control"].get("manual_step_deg", 1.0))
        self.manual_limit = float(
            config["control"].get("manual_tilt_limit_deg", 8.0)
        )
        self.manual_tilt_x = 0.0
        self.manual_tilt_y = 0.0

        pid_config = config["control"]["pid"]
        self.gains = {
            "kp": float(pid_config["kp"]),
            "ki": float(pid_config["ki"]),
            "kd": float(pid_config["kd"]),
        }
        self._gains_sent = None
        self._slider_max = {
            "kp": int(gui_config.get("kp_slider_max", 2000)),
            "ki": int(gui_config.get("ki_slider_max", 1000)),
            "kd": int(gui_config.get("kd_slider_max", 2000)),
        }
        self._trackbars_ready = False

        self.latest_frame = None
        self.latest_detection = None
        self.latest_ball_norm = None
        self._image_shape = (
            int(config["camera"].get("height", 480)),
            int(config["camera"].get("width", 640)),
        )
        self._message = "Listo. Presiona 1 o 2 para habilitar el control."
        self._message_color = (0, 255, 255)
        self._emergency_until = 0.0
        self.assistant: AxisAssistant | None = None

        self._create_window()
        self._send_gains(force=True)
        self._send_setpoint()
        self.link.send(format_mode(self.mode))
        if self.mode == 2:
            self._message = (
                "Modo automatico activo. El PID corre en el ESP32; "
                "ESPACIO para paro."
            )
        elif self.mode == 1:
            self._message = "Modo manual activo. Flechas para inclinar la placa."

    # --------------------------------------------------------------- ventana --
    def _create_window(self) -> None:
        cv2.namedWindow(self.window, cv2.WINDOW_AUTOSIZE)
        self._window_created = True
        cv2.setMouseCallback(self.window, self._on_mouse)

        for key, label in (("kp", "Kp x100"), ("ki", "Ki x100"), ("kd", "Kd x100")):
            initial = int(round(self.gains[key] * 100.0))
            initial = max(0, min(self._slider_max[key], initial))
            cv2.createTrackbar(
                label,
                self.window,
                initial,
                self._slider_max[key],
                self._on_gain_trackbar,
            )
        self._trackbars_ready = True

    def _on_gain_trackbar(self, _value=None) -> None:
        if not self._trackbars_ready:
            return
        try:
            kp = cv2.getTrackbarPos("Kp x100", self.window) / 100.0
            ki = cv2.getTrackbarPos("Ki x100", self.window) / 100.0
            kd = cv2.getTrackbarPos("Kd x100", self.window) / 100.0
        except cv2.error:
            return
        if min(kp, ki, kd) < 0.0:
            return
        self._set_gains(kp, ki, kd)

    def _set_gains(self, kp: float, ki: float, kd: float, force: bool = False) -> None:
        new_gains = (round(float(kp), 2), round(float(ki), 2), round(float(kd), 2))
        if not force and new_gains == self._gains_sent:
            return
        self.gains = {"kp": new_gains[0], "ki": new_gains[1], "kd": new_gains[2]}
        self._gains_sent = new_gains
        self.link.send(
            format_gains("B", self.gains["kp"], self.gains["ki"], self.gains["kd"])
        )

    def _send_gains(self, force: bool = False) -> None:
        self._set_gains(
            self.gains["kp"], self.gains["ki"], self.gains["kd"], force=force
        )

    def _send_setpoint(self) -> None:
        self.link.send(format_setpoint(self.setpoint_x, self.setpoint_y))

    # --------------------------------------------------------------- eventos --
    def process_events(self) -> None:
        try:
            raw = cv2.waitKeyEx(1)
        except (AttributeError, cv2.error):
            raw = cv2.waitKey(1)
        if raw == -1:
            self._check_window()
            return
        key = self._decode_key(raw)
        if key is not None:
            self.handle_key(key)
        self._check_window()

    @staticmethod
    def _decode_key(raw: int) -> str | None:
        if raw in ARROW_KEYS:
            return ARROW_KEYS[raw]
        code = raw & 0xFF
        if code in (13, 10):
            return "enter"
        if code == 27:
            return "escape"
        if code == 32:
            return " "
        if 33 <= code <= 126:
            return chr(code).lower()
        return None

    def _check_window(self) -> None:
        if not self._window_created:
            self.running = False
            return
        try:
            visible = cv2.getWindowProperty(self.window, cv2.WND_PROP_VISIBLE)
            if visible < 1:
                self.running = False
        except cv2.error:
            self.running = False

    def handle_key(self, key: str) -> None:
        if key == "q":
            self.running = False
            return

        if self.assistant is not None:
            if self.assistant.done:
                self.assistant = None
                self._message = "Asistente de ejes cerrado."
                self._message_color = (200, 200, 200)
                return
            if key in ("left", "right", "up", "down", "enter", "escape"):
                self.assistant.handle_key(key)
                if self.assistant.done:
                    self.mode = 0
                elif not self.assistant.active:
                    self.assistant = None
                    self.mode = 0
                    self._message = "Asistente de ejes cancelado."
                return
            if key == " ":
                self.assistant.cancel()
                self.assistant = None
                self.mode = 0
                self._message = "Asistente de ejes cancelado."
                return
            return

        # Un error de una ventana de calibración no debe tumbar la aplicación.
        try:
            if key == " ":
                self._enter_mode(0)
                self._emergency_until = time.monotonic() + 1.5
                self._message = "PARO DE EMERGENCIA: modo apagado."
                self._message_color = (0, 0, 255)
            elif key == "1":
                self._enter_mode(1)
            elif key == "2":
                self._enter_mode(2)
            elif key == "c":
                self._calibrate_color()
            elif key == "r":
                self._define_roi()
            elif key == "w":
                if self.link.connected:
                    self.link.send("W")
                    # Mantener sincronizadas las ganancias de la PC con la NVS
                    # del ESP32 para el próximo arranque.
                    self.config["control"]["pid"]["kp"] = self.gains["kp"]
                    self.config["control"]["pid"]["ki"] = self.gains["ki"]
                    self.config["control"]["pid"]["kd"] = self.gains["kd"]
                    self._save_config()
                    self._show_message(
                        "Guardado enviado al ESP32 (W) y sincronizado en config.json."
                    )
                else:
                    self._show_message("Sin enlace: no se pudo guardar W.", error=True)
            elif key == "p":
                roi = self.config["roi"]
                roi["perspective"] = not bool(roi.get("perspective", False))
                self._save_config()
                self._show_message(
                    "Perspectiva de ROI: "
                    + ("ACTIVADA" if roi["perspective"] else "DESACTIVADA")
                )
            elif key == "e":
                self._start_axis_assistant()
            elif key == "k":
                self._calibrate_servo_center()
            elif key == "d":
                self._configure_devices()
            elif key in ("left", "right", "up", "down"):
                self._move_manual(key)
        except (cv2.error, ValueError, OSError) as exc:
            self._show_message(f"Error en la ventana de calibración: {exc}", error=True)
            self._trackbars_ready = True

    def _show_message(self, text: str, error: bool = False) -> None:
        self._message = text
        self._message_color = (0, 0, 255) if error else (0, 255, 255)

    def _enter_mode(self, mode: int) -> None:
        if self.assistant is not None:
            self.assistant.cancel()
            self.assistant = None
        self.link.send(format_mode(mode))
        self.mode = mode
        if mode == 1:
            telemetry = self.link.latest_telemetry()
            if telemetry is not None:
                self.manual_tilt_x = float(telemetry.tilt_x)
                self.manual_tilt_y = float(telemetry.tilt_y)
            self._show_message("Modo manual. Flechas para inclinar la placa.")
        elif mode == 2:
            self._show_message("Modo automatico. PID en el ESP32.")
        else:
            self.manual_tilt_x = 0.0
            self.manual_tilt_y = 0.0
            self._show_message("Modo apagado: placa nivelada sin control.")

    def _move_manual(self, key: str) -> None:
        if self.mode != 1:
            self._show_message("Las flechas solo funcionan en modo manual (tecla 1).")
            return
        if key == "left":
            self.manual_tilt_x -= self.manual_step
        elif key == "right":
            self.manual_tilt_x += self.manual_step
        elif key == "up":
            self.manual_tilt_y += self.manual_step
        elif key == "down":
            self.manual_tilt_y -= self.manual_step
        self.manual_tilt_x = max(-self.manual_limit, min(self.manual_limit, self.manual_tilt_x))
        self.manual_tilt_y = max(-self.manual_limit, min(self.manual_limit, self.manual_tilt_y))
        self.link.send(format_tilt(self.manual_tilt_x, self.manual_tilt_y))
        self._show_message(
            f"Manual: tilt_x={self.manual_tilt_x:+.1f}  tilt_y={self.manual_tilt_y:+.1f}"
        )

    def _on_mouse(self, event, x, y, flags, param) -> None:
        del flags, param
        if event != cv2.EVENT_LBUTTONUP or self.latest_frame is None:
            return
        height, width = self.latest_frame.shape[:2]
        # Algunos backends también avisan clics sobre la zona de trackbars.
        if not (0 <= x < width and 0 <= y < height):
            return
        corners = corners_to_pixels(
            self.config["roi"]["corners_normalized"], width, height
        )
        if cv2.pointPolygonTest(corners, (float(x), float(y)), False) < 0:
            return
        try:
            nx, ny = normalize_point(
                x,
                y,
                corners,
                perspective=bool(self.config["roi"].get("perspective", False)),
                invert_x=bool(self.config["control"].get("invert_x", False)),
                invert_y=bool(self.config["control"].get("invert_y", False)),
            )
        except ValueError as exc:
            self._show_message(f"No se pudo convertir el clic: {exc}", error=True)
            return
        self.setpoint_x = nx
        self.setpoint_y = ny
        self._send_setpoint()
        self._show_message(f"Setpoint: x={nx:+.2f}  y={ny:+.2f}")

    # ------------------------------------------------------------ calibración --
    def _save_config(self) -> None:
        try:
            save_config(self.config, self.config_path)
        except (OSError, ValueError) as exc:
            self._show_message(f"No se pudo guardar config.json: {exc}", error=True)

    def _current_roi_mask(self):
        if self.latest_frame is None:
            return None
        height, width = self.latest_frame.shape[:2]
        corners = corners_to_pixels(
            self.config["roi"]["corners_normalized"], width, height
        )
        return corners, build_roi_mask((height, width, 3), corners)

    def _define_roi(self) -> None:
        if self.latest_frame is None:
            self._show_message("Todavía no hay imagen de cámara para marcar la ROI.")
            return
        height, width = self.latest_frame.shape[:2]
        current = corners_to_pixels(
            self.config["roi"]["corners_normalized"], width, height
        )
        selected = select_roi(self.latest_frame, current)
        if selected is None:
            self._show_message("Calibración de ROI cancelada.")
            return
        corners = pixels_to_normalized_corners(selected, width, height)
        self.config["roi"]["corners_normalized"] = corners
        self._save_config()
        self._show_message("ROI guardada en config.json.")

    def _calibrate_color(self) -> None:
        if self.latest_frame is None:
            self._show_message("Todavía no hay imagen de cámara para calibrar color.")
            return
        result = None
        roi = self._current_roi_mask()
        try:
            result = calibrate_hsv(
                self.latest_frame,
                self.config["vision"],
                roi_mask=roi[1] if roi else None,
            )
        finally:
            pass
        if result is None:
            self._show_message("Calibración de color cancelada.")
            return
        self.config["vision"] = result
        self._save_config()
        lower = result["hsv_lower"]
        upper = result["hsv_upper"]
        self._show_message(
            f"HSV guardado: inferior={lower} superior={upper}. "
            "Si no detecta bien, probá otra luz o ajustá área/circularidad."
        )

    def _start_axis_assistant(self) -> None:
        if not self.link.connected:
            self._show_message(
                "Conectá el ESP32 para usar el asistente de ejes.", error=True
            )
            return
        servo_config = self.config["simulation"]["servo"]
        self.assistant = AxisAssistant(
            self.link,
            tilt_deg=2.0,
            current_invert_x=bool(servo_config.get("invert_x", False)),
            current_invert_y=bool(servo_config.get("invert_y", False)),
        )
        self.assistant.start()
        self.mode = 1
        self._show_message("Asistente de ejes iniciado.")

    def _configure_devices(self) -> None:
        if self.simulation_mode:
            self._show_message(
                "En simulacion no hay camara ni puerto reales. "
                "Cerra esta ventana y usa ELEGIR_DISPOSITIVOS.bat."
            )
            return
        try:
            applied = setup_devices(self.config, self.config_path)
        except (cv2.error, RuntimeError) as exc:
            self._show_message(f"No se pudo abrir el selector: {exc}", error=True)
            return
        if applied:
            print("[gui] Dispositivos guardados. Reiniciando para aplicarlos...")
            self.restart_requested = True
            self.running = False
        else:
            self._show_message("Configuracion de dispositivos cancelada.")

    def _calibrate_servo_center(self) -> None:
        if not self.link.connected:
            self._show_message(
                "Conectá el ESP32 para calibrar el centro de los servos.",
                error=True,
            )
            return
        servo_config = self.config["simulation"]["servo"]
        result = servo_center_calibration(self.link, servo_config)
        self.mode = 0
        self.manual_tilt_x = 0.0
        self.manual_tilt_y = 0.0
        if result is None:
            self._show_message("Calibración de centro cancelada.")
        else:
            self._show_message(
                f"Offsets aplicados: X={result[0]:+.1f} deg, Y={result[1]:+.1f} deg"
            )

    # --------------------------------------------------------------- dibujo ---
    def render(
        self,
        frame,
        detection,
        ball_norm,
        camera_fps: float,
        vision_fps: float,
        processing_ms: float,
        latency_ms: float,
    ) -> None:
        if frame is None:
            height, width = self._image_shape
            image = np.zeros((height, width, 3), dtype=np.uint8)
            cv2.putText(
                image,
                "Esperando imagen de la camara...",
                (30, height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (200, 200, 200),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                "Revisa la camara del celular o usa --sim.",
                (30, height // 2 + 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (160, 160, 160),
                1,
                cv2.LINE_AA,
            )
        else:
            self.latest_frame = frame
            image = frame.copy()
            self._image_shape = image.shape[:2]

        self.latest_detection = detection
        self.latest_ball_norm = ball_norm
        height, width = image.shape[:2]

        self._draw_roi(image)
        self._draw_ball(image, detection)
        self._draw_setpoint(image)
        self._draw_hud(
            image,
            detection,
            ball_norm,
            camera_fps,
            vision_fps,
            processing_ms,
            latency_ms,
        )
        self._draw_footer(image)
        self._draw_message(image)
        self._draw_assistant(image)

        if time.monotonic() < self._emergency_until:
            cv2.rectangle(image, (0, height // 2 - 35), (width, height // 2 + 35),
                          (0, 0, 180), -1)
            cv2.putText(
                image,
                "PARO DE EMERGENCIA - MODO APAGADO",
                (width // 2 - 235, height // 2 + 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        try:
            cv2.imshow(self.window, image)
        except cv2.error:
            self.running = False

    def _draw_roi(self, image) -> None:
        height, width = image.shape[:2]
        try:
            corners = corners_to_pixels(
                self.config["roi"]["corners_normalized"], width, height
            )
        except ValueError:
            return
        cv2.polylines(
            image,
            [corners.astype(np.int32).reshape(-1, 1, 2)],
            True,
            (255, 220, 0),
            1,
            cv2.LINE_AA,
        )
        label = "ROI"
        if self.config["roi"].get("perspective", False):
            label += " + perspectiva"
        cv2.putText(
            image,
            label,
            (int(corners[0][0]) + 4, int(corners[0][1]) - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (255, 220, 0),
            1,
            cv2.LINE_AA,
        )

    def _draw_ball(self, image, detection) -> None:
        if detection is None or not detection.found:
            return
        center = (int(round(detection.cx)), int(round(detection.cy)))
        cv2.circle(image, center, max(4, int(round(detection.radius)) + 3),
                   (0, 255, 0), 2, cv2.LINE_AA)
        cv2.drawMarker(
            image, center, (0, 255, 0), cv2.MARKER_CROSS, 10, 1, cv2.LINE_AA
        )

    def _draw_setpoint(self, image) -> None:
        height, width = image.shape[:2]
        try:
            corners = corners_to_pixels(
                self.config["roi"]["corners_normalized"], width, height
            )
            px, py = denormalize_point(
                self.setpoint_x,
                self.setpoint_y,
                corners,
                perspective=bool(self.config["roi"].get("perspective", False)),
                invert_x=bool(self.config["control"].get("invert_x", False)),
                invert_y=bool(self.config["control"].get("invert_y", False)),
            )
        except ValueError:
            return
        x, y = int(round(px)), int(round(py))
        cv2.drawMarker(image, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 22, 2, cv2.LINE_AA)
        cv2.circle(image, (x, y), 10, (0, 0, 255), 1, cv2.LINE_AA)
        cv2.putText(
            image,
            "SP",
            (x + 12, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    def _draw_hud(
        self,
        image,
        detection,
        ball_norm,
        camera_fps,
        vision_fps,
        processing_ms,
        latency_ms,
    ) -> None:
        _height, width = image.shape[:2]
        telemetry = self.link.latest_telemetry() if self.link.connected else None
        state = telemetry.state if telemetry is not None else None
        state_name = STATE_NAMES.get(state, "SIN TELEMETRIA")
        mode_name = MODE_NAMES.get(self.mode, "?")
        link_text = (
            self.link.port_description if self.link.connected else "SIN ENLACE"
        )
        if self.link.connected and not telemetry:
            state_name = "ESPERANDO TELEMETRIA"

        panel_height = 145
        overlay = image.copy()
        cv2.rectangle(overlay, (0, 0), (width, panel_height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.62, image, 0.38, 0, image)

        line1 = f"MODO: {mode_name}   ESTADO: {state_name}   LINK: {link_text}"
        cv2.putText(image, _ascii(line1), (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                    0.48, (255, 255, 255), 1, cv2.LINE_AA)

        if telemetry is not None:
            line2 = (
                f"PELOTA x={telemetry.x:+.3f} y={telemetry.y:+.3f}   "
                f"SP x={self.setpoint_x:+.3f} y={self.setpoint_y:+.3f}"
            )
            line3 = (
                f"ERR x={telemetry.err_x:+.3f} y={telemetry.err_y:+.3f}   "
                f"TILT x={telemetry.tilt_x:+.2f} y={telemetry.tilt_y:+.2f} deg"
            )
            line4 = (
                f"SERVO x={telemetry.servo_x:.1f} y={telemetry.servo_y:.1f}   "
                f"IMU roll={telemetry.roll:+.1f} pitch={telemetry.pitch:+.1f}   "
                f"ESP {telemetry.ms} ms"
            )
        else:
            if ball_norm is None:
                detection_text = "no detectada"
            else:
                detection_text = f"x={ball_norm[0]:+.3f} y={ball_norm[1]:+.3f}"
            line2 = (
                f"VISION {detection_text}   "
                f"SP x={self.setpoint_x:+.3f} y={self.setpoint_y:+.3f}"
            )
            line3 = "ERR/TILT/SERVO: sin telemetria del ESP32"
            line4 = (
                f"GANANCIAS Kp={self.gains['kp']:.2f} "
                f"Ki={self.gains['ki']:.2f} Kd={self.gains['kd']:.2f}"
            )

        line5 = (
            f"CAM {camera_fps:.1f} fps   VISION {vision_fps:.1f} fps   "
            f"PROC {processing_ms:.1f} ms   LAT {latency_ms:.1f} ms"
        )
        for index, text in enumerate((line2, line3, line4, line5), start=1):
            color = (220, 255, 220) if index < 4 else (200, 220, 255)
            if detection is not None and not detection.found and index == 2:
                color = (0, 165, 255)
            cv2.putText(
                image,
                _ascii(text),
                (8, 20 + index * 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                color,
                1,
                cv2.LINE_AA,
            )

        if self.link.last_error and not self.link.connected:
            cv2.putText(
                image,
                _ascii(f"LINK: {self.link.last_error}")[:100],
                (8, panel_height + 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 120, 255),
                1,
                cv2.LINE_AA,
            )

    def _draw_footer(self, image) -> None:
        height, width = image.shape[:2]
        overlay = image.copy()
        cv2.rectangle(overlay, (0, height - 58), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.65, image, 0.35, 0, image)
        lines = [
            "Q salir | ESPACIO paro | 1 manual | 2 auto | R ROI | C color | P perspectiva",
            "D camara/puerto | W guardar ESP32 | E ejes | K centro servos | flechas | clic setpoint",
        ]
        for index, text in enumerate(lines):
            cv2.putText(
                image,
                _ascii(text),
                (8, height - 38 + index * 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.39,
                (230, 230, 230),
                1,
                cv2.LINE_AA,
            )

    def _draw_message(self, image) -> None:
        height = image.shape[0]
        if self.assistant is not None:
            return
        message = _ascii(self._message)[:105]
        cv2.putText(
            image,
            message,
            (8, height - 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            self._message_color,
            1,
            cv2.LINE_AA,
        )

    def _draw_assistant(self, image) -> None:
        if self.assistant is None:
            return
        lines = self.assistant.overlay_lines()
        if not lines:
            return
        height, width = image.shape[:2]
        line_count = len(lines)
        panel_height = 22 * line_count + 18
        top = max(130, height - 58 - panel_height - 8)
        overlay = image.copy()
        cv2.rectangle(overlay, (0, top), (width, top + panel_height), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.8, image, 0.2, 0, image)
        for index, text in enumerate(lines):
            color = (0, 255, 255) if index == 0 else (240, 240, 240)
            cv2.putText(
                image,
                _ascii(text),
                (10, top + 24 + index * 21),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                color,
                1,
                cv2.LINE_AA,
            )

    # --------------------------------------------------------------- cierre ---
    def close(self) -> None:
        if self._window_created:
            try:
                cv2.destroyWindow(self.window)
            except cv2.error:
                pass
            self._window_created = False
