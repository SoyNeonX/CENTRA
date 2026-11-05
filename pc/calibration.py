"""
Herramientas de calibración asistida:

- Calibrador de color HSV con trackbars y vista previa de la máscara.
- Asistente para decidir el sentido de cada eje.
- Calibración del centro de los servos con los comandos V y C.

Las funciones que abren ventanas usan OpenCV HighGUI. La calibración real del
color, de los ejes y de los servos es una prueba de hardware (ver
HARDWARE_TEST.md); acá solo se implementan las herramientas.
"""

from __future__ import annotations

import cv2
import numpy as np
from protocol import format_mode, format_offsets, format_raw_servo, format_tilt

# TODO-HW: ejecutar cada asistente con la cámara y los servos reales.


def _safe_destroy_window(window: str) -> None:
    """Cerrar una ventana no debe romper la aplicación si ya estaba cerrada."""
    try:
        cv2.destroyWindow(window)
    except cv2.error:
        pass


def calibrate_hsv(frame, vision_config: dict, plate_mask=None):
    """
    Muestra trackbars HSV y una vista previa de la máscara. Devuelve un nuevo
    diccionario de visión o None si se cancela. El guardado en config.json lo
    hace la GUI para no mezclar responsabilidades.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None

    window = "Calibrar color HSV"
    lower = [int(value) for value in vision_config["hsv_lower"]]
    upper = [int(value) for value in vision_config["hsv_upper"]]
    lower[0] = min(179, max(0, lower[0]))
    upper[0] = min(179, max(0, upper[0]))
    for i in (1, 2):
        lower[i] = min(255, max(0, lower[i]))
        upper[i] = min(255, max(0, upper[i]))

    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
    cv2.createTrackbar("Hmin", window, lower[0], 179, lambda _v: None)
    cv2.createTrackbar("Hmax", window, upper[0], 179, lambda _v: None)
    cv2.createTrackbar("Smin", window, lower[1], 255, lambda _v: None)
    cv2.createTrackbar("Smax", window, upper[1], 255, lambda _v: None)
    cv2.createTrackbar("Vmin", window, lower[2], 255, lambda _v: None)
    cv2.createTrackbar("Vmax", window, upper[2], 255, lambda _v: None)

    result = None
    try:
        while True:
            hmin = cv2.getTrackbarPos("Hmin", window)
            hmax = cv2.getTrackbarPos("Hmax", window)
            smin = cv2.getTrackbarPos("Smin", window)
            smax = cv2.getTrackbarPos("Smax", window)
            vmin = cv2.getTrackbarPos("Vmin", window)
            vmax = cv2.getTrackbarPos("Vmax", window)

            # Corregir cruces de forma visible para el usuario.
            if hmin > hmax:
                cv2.setTrackbarPos("Hmax", window, hmin)
                hmax = hmin
            if smin > smax:
                cv2.setTrackbarPos("Smax", window, smin)
                smax = smin
            if vmin > vmax:
                cv2.setTrackbarPos("Vmax", window, vmin)
                vmax = vmin

            preview_config = {
                **vision_config,
                "hsv_lower": [hmin, smin, vmin],
                "hsv_upper": [hmax, smax, vmax],
            }
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(
                hsv,
                np.array([hmin, smin, vmin], dtype=np.uint8),
                np.array([hmax, smax, vmax], dtype=np.uint8),
            )
            if plate_mask is not None:
                mask = cv2.bitwise_and(mask, plate_mask)

            from vision import detect_ball

            detection = detect_ball(frame, preview_config, plate_mask=plate_mask)
            color_view = frame.copy()
            if detection.found:
                cv2.circle(
                    color_view,
                    (int(detection.cx), int(detection.cy)),
                    int(max(4, detection.radius)),
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
            mask_view = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            preview = np.hstack([color_view, mask_view])

            header = np.zeros((58, preview.shape[1], 3), dtype=np.uint8)
            cv2.putText(
                header,
                "Ajusta H, S y V hasta que solo la pelota quede blanca en la mascara de la placa",
                (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                header,
                f"Rango actual: H[{hmin},{hmax}] S[{smin},{smax}] V[{vmin},{vmax}]"
                "  | ENTER/S guarda, ESC/Q cancela",
                (8, 46),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.47,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )
            composite = np.vstack([header, preview])
            cv2.imshow(window, composite)
            key = cv2.waitKey(20) & 0xFF
            if key in (13, 10, ord("s"), ord("S")):
                result = {
                    **vision_config,
                    "hsv_lower": [int(hmin), int(smin), int(vmin)],
                    "hsv_upper": [int(hmax), int(smax), int(vmax)],
                }
                break
            if key in (27, ord("q"), ord("Q")):
                break
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        _safe_destroy_window(window)
    return result


def servo_center_calibration(link, servo_config: dict, window="Calibrar centro de servos"):
    """
    Mueve los servos con V y calcula el offset que los deja nivelados.

    Controles:
      - Trackbars: ángulo crudo de cada servo.
      - ENTER: aplica C con los offsets hallados (sin guardar).
      - S: aplica C y manda W para guardar en la NVS del ESP32.
      - ESC/Q: cancela.

    Devuelve (offset_x, offset_y) si se aceptó, o None si se canceló.
    Esta función requiere hardware real para tener efecto.
    """
    min_deg = round(float(servo_config["min_deg"]))
    max_deg = round(float(servo_config["max_deg"]))
    center_deg = float(servo_config["center_deg"])
    offset_limit = abs(float(servo_config["offset_limit_deg"]))
    span = max(1, max_deg - min_deg)

    telemetry = link.latest_telemetry()
    if telemetry is not None:
        initial_x = round(telemetry.servo_x)
        initial_y = round(telemetry.servo_y)
    else:
        initial_x = round(center_deg)
        initial_y = round(center_deg)
    initial_x = max(min_deg, min(max_deg, initial_x))
    initial_y = max(min_deg, min(max_deg, initial_y))

    link.send(format_mode(1))
    link.send(format_raw_servo(initial_x, initial_y))

    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
    cv2.createTrackbar("Angulo X", window, initial_x - min_deg, span, lambda _v: None)
    cv2.createTrackbar("Angulo Y", window, initial_y - min_deg, span, lambda _v: None)

    last_sent = (None, None)
    result = None
    try:
        while True:
            raw_x = cv2.getTrackbarPos("Angulo X", window) + min_deg
            raw_y = cv2.getTrackbarPos("Angulo Y", window) + min_deg
            if (raw_x, raw_y) != last_sent:
                link.send(format_raw_servo(raw_x, raw_y))
                last_sent = (raw_x, raw_y)

            offset_x = max(-offset_limit, min(offset_limit, raw_x - center_deg))
            offset_y = max(-offset_limit, min(offset_limit, raw_y - center_deg))
            canvas = np.zeros((410, 720, 3), dtype=np.uint8)
            lines = [
                "Calibracion del centro de los servos",
                "1) Mueve cada trackbar hasta que la placa quede nivelada de verdad.",
                "2) Mira la placa de frente, con la pelota quieta o sin pelota.",
                f"Servo X crudo: {raw_x} deg  -> offset {offset_x:+.1f} deg",
                f"Servo Y crudo: {raw_y} deg  -> offset {offset_y:+.1f} deg",
                "ENTER aplica C | S aplica C y guarda con W | ESC/Q cancela",
                "Al salir se manda M,0 y la placa vuelve a nivel con el offset nuevo.",
            ]
            for index, text in enumerate(lines):
                color = (0, 255, 255) if index == 0 else (235, 235, 235)
                scale = 0.62 if index == 0 else 0.5
                cv2.putText(
                    canvas,
                    text,
                    (16, 36 + index * 42),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    scale,
                    color,
                    1,
                    cv2.LINE_AA,
                )
            cv2.putText(
                canvas,
                "TODO-HW: esta calibracion solo tiene efecto con el ESP32 conectado.",
                (16, canvas.shape[0] - 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (120, 180, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.imshow(window, canvas)
            key = cv2.waitKey(20) & 0xFF
            if key in (13, 10, ord("s"), ord("S")):
                link.send(format_offsets(offset_x, offset_y))
                if key in (ord("s"), ord("S")):
                    link.send("W")
                result = (offset_x, offset_y)
                break
            if key in (27, ord("q"), ord("Q")):
                break
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        link.send(format_tilt(0.0, 0.0))
        link.send(format_mode(0))
        _safe_destroy_window(window)
    return result


class AxisAssistant:
    """
    Guía no bloqueante para determinar el sentido de los servos.

    Se usa desde la GUI (tecla E): mueve la placa en modo manual y espera a
    que el usuario indique hacia dónde rueda la pelota. Al final la GUI
    aplica la inversión en el software de la PC; no se recompila el firmware.
    """

    def __init__(
        self,
        link,
        tilt_deg: float = 2.0,
        current_invert_x: bool = False,
        current_invert_y: bool = False,
    ):
        self.link = link
        self.tilt_deg = abs(float(tilt_deg))
        self.current_invert_x = bool(current_invert_x)
        self.current_invert_y = bool(current_invert_y)
        self.active = False
        self.done = False
        self.stage = "idle"
        self.invert_x = None
        self.invert_y = None
        self.message = ""

    def start(self) -> None:
        self.active = True
        self.done = False
        self.stage = "x"
        self.invert_x = None
        self.invert_y = None
        self.message = "Probando el eje X"
        self.link.send(format_mode(1))
        self.link.send(format_tilt(self.tilt_deg, 0.0))

    def cancel(self) -> None:
        if self.active or self.done:
            self.link.send(format_tilt(0.0, 0.0))
            self.link.send(format_mode(0))
        self.active = False
        self.done = False
        self.stage = "idle"
        self.message = "Asistente cancelado"

    def handle_key(self, key: str | None) -> None:
        if not self.active or key is None:
            return

        if key == "escape":
            self.cancel()
            return

        if self.stage == "x" and key in ("left", "right"):
            # La convención es que +X acelere a la derecha. Si el sentido actual
            # ya es correcto se conserva la bandera; si no, se invierte.
            if key == "right":
                self.invert_x = self.current_invert_x
            else:
                self.invert_x = not self.current_invert_x
            self.stage = "wait_y"
            self.message = (
                "Eje X listo. La placa vuelve a nivel; esperá a que la pelota "
                "se detenga y presiona ENTER para probar Y."
            )
            self.link.send(format_tilt(0.0, 0.0))
            return

        if self.stage == "wait_y" and key == "enter":
            self.stage = "y"
            self.message = "Probando el eje Y"
            self.link.send(format_tilt(0.0, self.tilt_deg))
            return

        if self.stage == "y" and key in ("up", "down"):
            # La convención es que +Y acelere hacia arriba.
            if key == "up":
                self.invert_y = self.current_invert_y
            else:
                self.invert_y = not self.current_invert_y
            self.active = False
            self.done = True
            self.stage = "done"
            self.link.send(format_tilt(0.0, 0.0))
            self.link.send(format_mode(0))
            self.message = (
                "Listo. La app aplicará la inversión al cerrar este mensaje. "
                f"X={'ON' if self.invert_x else 'OFF'}, "
                f"Y={'ON' if self.invert_y else 'OFF'}. No recompiles."
            )
            print("\n[ejes] Inversión calculada para el software de la PC:")
            print(f"[ejes]   invert_x = {'true' if self.invert_x else 'false'}")
            print(f"[ejes]   invert_y = {'true' if self.invert_y else 'false'}")
            print(
                "[ejes] Se aplica a control.invert_x/y y simulation.servo.invert_x/y."
                " No requiere PlatformIO.\n"
            )

    def overlay_lines(self) -> list[str]:
        if not self.active and not self.done:
            return []
        if self.done:
            return [
                "ASISTENTE DE EJES TERMINADO",
                self.message,
                "Presioná cualquier tecla para cerrar este mensaje.",
            ]
        if self.stage == "x":
            return [
                "ASISTENTE DE EJES - PASO 1/2: X",
                (
                    "Inversión actual en el software: "
                    f"X={'ON' if self.current_invert_x else 'OFF'}, "
                    f"Y={'ON' if self.current_invert_y else 'OFF'}."
                ),
                f"La placa se inclinó +{self.tilt_deg:.1f}° en X.",
                "Si la pelota rueda a la DERECHA: flecha DERECHA.",
                "Si rueda a la IZQUIERDA: flecha IZQUIERDA.  ESC cancela.",
            ]
        if self.stage == "wait_y":
            return [
                "ASISTENTE DE EJES - X registrado",
                "Esperá a que la pelota se detenga.",
                "ENTER: probar el eje Y.  ESC cancela.",
            ]
        if self.stage == "y":
            return [
                "ASISTENTE DE EJES - PASO 2/2: Y",
                f"La placa se inclinó +{self.tilt_deg:.1f}° en Y.",
                "Si la pelota rueda hacia ARRIBA: flecha ARRIBA.",
                "Si rueda hacia ABAJO: flecha ABAJO.  ESC cancela.",
            ]
        return []
