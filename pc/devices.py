"""
Selector visual de cámara y puerto serial.

No abre las cámaras para probarlas (eso podría bloquear o chocar con la cámara
en uso). Muestra los índices disponibles y los puertos COM detectados; el
usuario elige y el programa guarda `config.json`. Al aplicar, la aplicación se
reinicia para que los cambios tengan efecto.
"""

from __future__ import annotations

import copy
import unicodedata
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np
from serial.tools import list_ports

from config import save_config

AUTO_PORT = "__AUTO__"
WINDOW_NAME = "Configurar camara y puerto"
CAMERA_INDICES = [0, 1, 2, 3, 4]


class SerialPort(NamedTuple):
    device: str
    description: str


def list_serial_ports() -> list[SerialPort]:
    """Devuelve los puertos que Windows expone en este momento, sin abrirlos."""
    try:
        ports = sorted(list_ports.comports(), key=lambda item: item.device)
    except Exception:
        return []
    result = []
    for info in ports:
        device = getattr(info, "device", "") or ""
        if not device:
            continue
        description = getattr(info, "description", "") or "puerto serial"
        result.append(SerialPort(device, description))
    return result


def normalize_camera_source(source):
    """Acepta 0, "0" o una URL http/https/rtsp. Lanza ValueError si no sirve."""
    if isinstance(source, bool):
        raise ValueError("La fuente de camara no es valida")
    if isinstance(source, int):
        if source < 0:
            raise ValueError("El indice de camara debe ser 0 o mayor")
        return source
    text = str(source).strip()
    if not text:
        raise ValueError("La fuente de camara esta vacia")
    if text.isdigit():
        return int(text)
    if "://" not in text:
        raise ValueError("La URL debe incluir http://, https:// o rtsp://")
    return text


def apply_device_config(config: dict, camera_source, serial_port: str) -> dict:
    """
    Aplica los valores elegidos a una copia de `config` y la devuelve.
    `serial_port` puede ser AUTO_PORT o un COM concreto.
    """
    updated = copy.deepcopy(config)
    updated.setdefault("camera", {})["source"] = normalize_camera_source(camera_source)
    updated.setdefault("serial", {})
    if serial_port == AUTO_PORT or not str(serial_port).strip():
        updated["serial"]["port"] = ""
        updated["serial"]["auto_detect"] = True
    else:
        updated["serial"]["port"] = str(serial_port).strip()
        updated["serial"]["auto_detect"] = False
    updated["setup_completed"] = True
    return updated


def _text(image, text, position, scale=0.5, color=(235, 235, 235), thickness=1):
    # Las fuentes Hershey de OpenCV no renderizan acentos.
    ascii_text = (
        unicodedata.normalize("NFKD", str(text))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    cv2.putText(
        image,
        ascii_text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def _inside(x, y, rect) -> bool:
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def setup_devices(
    config: dict,
    config_path: str | Path,
    window_title: str = WINDOW_NAME,
) -> bool:
    """
    Abre el selector y guarda `config.json` si el usuario acepta.

    Devuelve True si guardó, False si canceló. No necesita cámara ni ESP32.
    """
    config_path = Path(config_path)
    raw_camera = config.get("camera", {}).get("source", 0)
    try:
        camera_source = normalize_camera_source(raw_camera)
    except ValueError:
        camera_source = 0

    camera_choices = list(CAMERA_INDICES)
    if isinstance(camera_source, int) and camera_source not in camera_choices:
        camera_choices.append(camera_source)

    if isinstance(camera_source, str):
        selected_camera = "url"
        url_text = camera_source
    else:
        selected_camera = camera_source
        url_text = ""

    saved_port = str(config.get("serial", {}).get("port", "") or "").strip()
    selected_port = saved_port or AUTO_PORT
    ports = list_serial_ports()
    prior_camera = selected_camera
    state = {
        "url_editing": False,
        "click": None,
        "message": "Elegi una camara y un puerto. Despues guarda.",
        "error": False,
    }
    layout = {"rows": [], "buttons": []}

    def on_mouse(event, x, y, flags, param):
        del flags, param
        if event == cv2.EVENT_LBUTTONDOWN:
            state["click"] = (int(x), int(y))

    try:
        cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)
    except cv2.error as exc:
        raise RuntimeError(
            f"No se pudo abrir la ventana de configuracion: {exc}"
        ) from exc
    cv2.setMouseCallback(window_title, on_mouse)

    def refresh_ports() -> None:
        nonlocal ports
        ports = list_serial_ports()
        state["message"] = f"Puertos actualizados: {len(ports)} encontrados."
        state["error"] = False

    def show_error(text: str) -> None:
        state["message"] = text
        state["error"] = True

    def try_apply() -> bool:
        try:
            chosen_camera = (
                normalize_camera_source(url_text)
                if selected_camera == "url"
                else int(selected_camera)
            )
        except ValueError as exc:
            show_error(str(exc))
            return False

        updated = apply_device_config(config, chosen_camera, selected_port)
        try:
            save_config(updated, config_path)
        except (OSError, ValueError) as exc:
            show_error(f"No se pudo guardar config.json: {exc}")
            return False

        config.clear()
        config.update(updated)
        print(
            "[dispositivos] Guardado: camara="
            f"{updated['camera']['source']!r}, serial="
            f"{updated['serial']['port'] or 'autodetect'}"
        )
        return True

    result = False
    try:
        while True:
            image = np.full((650, 1000, 3), 25, dtype=np.uint8)
            cv2.rectangle(image, (0, 0), (1000, 78), (45, 45, 55), -1)
            _text(
                image,
                "CONFIGURACION DE CAMARA Y PUERTO SERIAL",
                (28, 34),
                0.8,
                (255, 255, 255),
                2,
            )
            _text(
                image,
                "Mouse: elegi una fila. Teclas: U=URL, R=actualizar, ENTER=guardar, ESC=cancelar.",
                (28, 61),
                0.45,
                (200, 200, 200),
            )
            layout = {"rows": [], "buttons": []}

            # ------------------------------- CAMARA -----------------------------
            _text(image, "CAMARA", (32, 112), 0.62, (0, 220, 255), 2)
            row_y = 128
            for index in camera_choices:
                rect = (30, row_y, 470, row_y + 34)
                selected = selected_camera == index and not state["url_editing"]
                fill = (40, 90, 60) if selected else (38, 38, 44)
                cv2.rectangle(image, (rect[0], rect[1]), (rect[2], rect[3]), fill, -1)
                cv2.rectangle(
                    image,
                    (rect[0], rect[1]),
                    (rect[2], rect[3]),
                    (0, 230, 120) if selected else (80, 80, 90),
                    1,
                )
                cv2.circle(
                    image,
                    (49, row_y + 17),
                    7,
                    (0, 230, 120) if selected else (140, 140, 150),
                    -1 if selected else 1,
                    cv2.LINE_AA,
                )
                _text(
                    image,
                    f"Indice {index}  (probar si es DroidCam/Iriun)",
                    (68, row_y + 23),
                    0.52,
                )
                layout["rows"].append(("camera", index, rect))
                row_y += 38

            url_top = row_y + 8
            _text(
                image,
                "URL de stream (IP Webcam / RTSP)",
                (32, url_top + 2),
                0.45,
                (190, 190, 190),
            )
            url_rect = (30, url_top + 14, 470, url_top + 54)
            url_selected = selected_camera == "url"
            border = (
                (0, 220, 255)
                if state["url_editing"]
                else ((0, 230, 120) if url_selected else (80, 80, 90))
            )
            cv2.rectangle(
                image,
                (url_rect[0], url_rect[1]),
                (url_rect[2], url_rect[3]),
                (48, 48, 55),
                -1,
            )
            cv2.rectangle(
                image,
                (url_rect[0], url_rect[1]),
                (url_rect[2], url_rect[3]),
                border,
                2 if url_selected else 1,
            )
            if url_text:
                _text(image, url_text[-64:], (40, url_top + 41), 0.5)
            else:
                _text(
                    image,
                    "http://192.168.0.50:8080/video",
                    (40, url_top + 41),
                    0.5,
                    (130, 130, 140),
                )
            if state["url_editing"]:
                cursor_x = 40 + min(len(url_text), 64) * 9
                cv2.line(
                    image,
                    (cursor_x, url_top + 24),
                    (cursor_x, url_top + 47),
                    (0, 220, 255),
                    1,
                )
                _text(
                    image,
                    "Escribi la URL. ENTER termina de editar; ESC cancela la edicion.",
                    (32, url_top + 74),
                    0.43,
                    (0, 220, 255),
                )
            layout["rows"].append(("url", "url", url_rect))

            # ---------------------------- PUERTO SERIAL -------------------------
            _text(image, "PUERTO SERIAL", (525, 112), 0.62, (0, 220, 255), 2)
            serial_rows = [SerialPort(AUTO_PORT, "Autodetectar (recomendado)")]
            detected = {port.device for port in ports}
            for extra in (saved_port, selected_port):
                if (
                    extra
                    and extra != AUTO_PORT
                    and extra not in detected
                    and all(item.device != extra for item in serial_rows)
                ):
                    serial_rows.append(SerialPort(extra, "guardado / no detectado"))
            serial_rows.extend(ports)

            row_y = 128
            for port in serial_rows:
                rect = (520, row_y, 970, row_y + 36)
                selected = selected_port == port.device
                fill = (40, 90, 60) if selected else (38, 38, 44)
                cv2.rectangle(image, (rect[0], rect[1]), (rect[2], rect[3]), fill, -1)
                cv2.rectangle(
                    image,
                    (rect[0], rect[1]),
                    (rect[2], rect[3]),
                    (0, 230, 120) if selected else (80, 80, 90),
                    1,
                )
                cv2.circle(
                    image,
                    (539, row_y + 18),
                    7,
                    (0, 230, 120) if selected else (140, 140, 150),
                    -1 if selected else 1,
                    cv2.LINE_AA,
                )
                label = (
                    "AUTODETECTAR (recomendado)"
                    if port.device == AUTO_PORT
                    else f"{port.device}  {port.description[:34]}"
                )
                _text(image, label, (558, row_y + 23), 0.48)
                layout["rows"].append(("serial", port.device, rect))
                row_y += 40
                if row_y > 430:
                    break

            if not ports:
                _text(
                    image,
                    "No se detectaron puertos COM.",
                    (525, row_y + 22),
                    0.48,
                    (0, 160, 255),
                )
                _text(
                    image,
                    "Conecta el ESP32, instala el driver y presiona R.",
                    (525, row_y + 46),
                    0.42,
                    (220, 180, 100),
                )

            # ------------------------------- BOTONES ----------------------------
            buttons = [
                ("r", (30, 560, 200, 602), "R  ACTUALIZAR", (80, 130, 180)),
                ("esc", (560, 560, 730, 602), "ESC  CANCELAR", (100, 80, 80)),
                ("enter", (750, 560, 970, 602), "ENTER  GUARDAR", (40, 150, 80)),
            ]
            for action, rect, label, color in buttons:
                cv2.rectangle(image, (rect[0], rect[1]), (rect[2], rect[3]), color, -1)
                _text(image, label, (rect[0] + 18, rect[1] + 27), 0.5, (255, 255, 255))
                layout["buttons"].append((action, rect))

            _text(
                image,
                state["message"][:125],
                (32, 530),
                0.46,
                (0, 120, 255) if state["error"] else (210, 220, 230),
            )
            _text(
                image,
                "Nota: no se prueba la camara. Si un indice no abre, elegi otro y revisa la app.",
                (32, 628),
                0.39,
                (160, 160, 170),
            )

            cv2.imshow(window_title, image)
            key = cv2.waitKeyEx(20)
            apply_requested = False
            cancel_requested = False

            # -------------------------------- mouse -----------------------------
            click = state["click"]
            state["click"] = None
            if click is not None:
                x, y = click
                for kind, value, rect in layout["rows"]:
                    if not _inside(x, y, rect):
                        continue
                    if kind == "camera":
                        state["url_editing"] = False
                        selected_camera = value
                        state["message"] = f"Camara seleccionada: indice {value}."
                        state["error"] = False
                    elif kind == "serial":
                        selected_port = value
                        state["message"] = (
                            "Puerto: autodetectar."
                            if value == AUTO_PORT
                            else f"Puerto seleccionado: {value}."
                        )
                        state["error"] = False
                    elif kind == "url":
                        prior_camera = selected_camera
                        selected_camera = "url"
                        state["url_editing"] = True
                        state["message"] = (
                            "Escribi la URL y presiona ENTER para terminar la edicion."
                        )
                        state["error"] = False
                    break
                else:
                    for action, rect in layout["buttons"]:
                        if not _inside(x, y, rect):
                            continue
                        if action == "r":
                            refresh_ports()
                        elif action == "esc":
                            cancel_requested = True
                        elif action == "enter":
                            apply_requested = True
                        break

            # ------------------------------ teclado -----------------------------
            if key != -1:
                if state["url_editing"]:
                    if key in (13, 10):
                        state["url_editing"] = False
                        state["message"] = (
                            "URL lista. Presiona ENTER de nuevo para guardar."
                        )
                    elif key == 27:
                        state["url_editing"] = False
                        if not url_text and isinstance(prior_camera, int):
                            selected_camera = prior_camera
                        state["message"] = "Edicion de URL cancelada."
                    elif key in (8, 127):
                        url_text = url_text[:-1]
                    elif 32 <= key <= 126:
                        url_text += chr(key)
                        selected_camera = "url"
                        state["error"] = False
                        if len(url_text) > 180:
                            url_text = url_text[:180]
                else:
                    if key in (13, 10):
                        apply_requested = True
                    elif key == 27:
                        cancel_requested = True
                    elif 32 <= key <= 126:
                        char = chr(key).lower()
                        if char == "r":
                            refresh_ports()
                        elif char == "u":
                            prior_camera = selected_camera
                            selected_camera = "url"
                            state["url_editing"] = True
                            state["message"] = (
                                "Escribi la URL y presiona ENTER para terminar "
                                "la edicion."
                            )
                            state["error"] = False

            if cancel_requested:
                break
            if apply_requested and try_apply():
                result = True
                break

            try:
                if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        try:
            cv2.destroyWindow(window_title)
        except cv2.error:
            pass

    return result
