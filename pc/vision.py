"""
Detección de la pelota por color HSV dentro de la placa.

La placa y su máscara las define markers.py a partir de los cuatro ArUco.
"""

from __future__ import annotations

from typing import NamedTuple

import cv2
import numpy as np

# TODO-HW: validar el rango HSV con la luz y la cámara reales.


class BallDetection(NamedTuple):
    """Resultado de detect_ball. Se puede desempaquetar: (cx, cy, radio, found)."""

    cx: float
    cy: float
    radius: float
    found: bool


def _odd_kernel(value: int, minimum: int = 1) -> int:
    value = max(minimum, int(value))
    return value if value % 2 == 1 else value + 1


def detect_ball(frame, vision_config: dict, plate_mask=None) -> BallDetection:
    """
    Detecta la pelota naranja.

    Parámetros
    ----------
    frame:
        Imagen BGR de OpenCV.
    vision_config:
        Diccionario con hsv_lower, hsv_upper, blur_kernel, morph_kernel,
        min_area, max_area y min_circularity.
    plate_mask:
        Máscara opcional uint8 del tamaño del cuadro. Solo se analiza dentro
        de la placa.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return BallDetection(0.0, 0.0, 0.0, False)

    lower = np.array(vision_config["hsv_lower"], dtype=np.uint8)
    upper = np.array(vision_config["hsv_upper"], dtype=np.uint8)
    blur_size = _odd_kernel(vision_config.get("blur_kernel", 5))
    morph_size = _odd_kernel(vision_config.get("morph_kernel", 5))
    min_area = float(vision_config.get("min_area", 150))
    max_area = float(vision_config.get("max_area", 12000))
    min_circularity = float(vision_config.get("min_circularity", 0.55))

    # Suavizar el color antes de umbralizar conserva mejor el tamaño del
    # contorno que desenfocar directamente la máscara binaria.
    working = cv2.GaussianBlur(frame, (blur_size, blur_size), 0) if blur_size > 1 else frame
    hsv = cv2.cvtColor(working, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower, upper)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_size, morph_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    if plate_mask is not None:
        if plate_mask.shape[:2] != mask.shape[:2]:
            raise ValueError("La máscara de placa no coincide con el cuadro")
        mask = cv2.bitwise_and(mask, plate_mask)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_circularity = -1.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area or area > max_area:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0.0:
            continue
        circularity = 4.0 * np.pi * area / (perimeter * perimeter)
        if circularity < min_circularity:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] <= 0.0:
            continue
        if circularity > best_circularity:
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]
            radius = float(np.sqrt(area / np.pi))
            best = BallDetection(float(cx), float(cy), radius, True)
            best_circularity = circularity

    if best is None:
        return BallDetection(0.0, 0.0, 0.0, False)
    return best
