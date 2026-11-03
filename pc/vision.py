"""
Detección de la pelota y geometría de la placa.

- La detección trabaja en HSV y elige el contorno más circular dentro de un
  rango de área.
- La ROI es un cuadrilátero de 4 esquinas. Se puede normalizar con una
  homografía opcional (perspectiva) para corregir una cámara que no está
  perfectamente perpendicular a la placa.
- La convención final es +X a la derecha de la imagen y +Y hacia arriba.
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


def detect_ball(frame, vision_config: dict, roi_mask=None) -> BallDetection:
    """
    Detecta la pelota naranja.

    Parámetros
    ----------
    frame:
        Imagen BGR de OpenCV.
    vision_config:
        Diccionario con hsv_lower, hsv_upper, blur_kernel, morph_kernel,
        min_area, max_area y min_circularity.
    roi_mask:
        Máscara opcional uint8 del tamaño del cuadro. Solo se analiza ahí.
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

    if roi_mask is not None:
        if roi_mask.shape[:2] != mask.shape[:2]:
            raise ValueError("La máscara de ROI no coincide con el tamaño del cuadro")
        mask = cv2.bitwise_and(mask, roi_mask)

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


def order_corners(points) -> np.ndarray:
    """
    Ordena 4 puntos como [arriba-izquierda, arriba-derecha,
    abajo-derecha, abajo-izquierda].

    Es tolerante al orden en que el usuario hizo los clics para una placa
    vista de frente o levemente en perspectiva.
    """
    pts = np.asarray(points, dtype=np.float32)
    if pts.shape != (4, 2):
        raise ValueError("Se necesitan exactamente 4 puntos (x, y)")

    sums = pts.sum(axis=1)
    differences = pts[:, 1] - pts[:, 0]  # y - x
    top_left = pts[np.argmin(sums)]
    bottom_right = pts[np.argmax(sums)]
    top_right = pts[np.argmin(differences)]
    bottom_left = pts[np.argmax(differences)]

    ordered = np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)
    # Si dos esquinas se repitieron por una placa muy rotada, no se puede armar
    # una homografía válida; se avisa para que el usuario vuelva a marcar.
    if len({(float(p[0]), float(p[1])) for p in ordered}) != 4:
        raise ValueError("Las esquinas de la ROI no son cuatro puntos distintos")
    return ordered


def corners_to_pixels(corners_normalized, width: int, height: int) -> np.ndarray:
    """Convierte las 4 esquinas guardadas en [0,1] a píxeles del cuadro actual."""
    points = np.asarray(corners_normalized, dtype=np.float32).copy()
    if points.shape != (4, 2):
        raise ValueError("La ROI debe tener 4 pares [x, y] normalizados")
    points[:, 0] *= float(width)
    points[:, 1] *= float(height)
    return order_corners(points)


def pixels_to_normalized_corners(points, width: int, height: int):
    """Convierte 4 clics en píxeles a la lista [[x, y], ...] que va al JSON."""
    ordered = order_corners(points)
    normalized = ordered / np.array([width, height], dtype=np.float32)
    return [[float(x), float(y)] for x, y in normalized]


def build_roi_mask(frame_shape, corners_pixels) -> np.ndarray:
    """Máscara blanca dentro de la ROI y negra fuera."""
    height, width = frame_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    points = np.asarray(corners_pixels, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [points], 255)
    return mask


def _square_transform(corners_pixels) -> tuple[np.ndarray, np.ndarray, float]:
    """Homografía desde las 4 esquinas al cuadrado [0,1000]²."""
    corners = order_corners(corners_pixels)
    side = 1000.0
    destination = np.array(
        [[0.0, 0.0], [side, 0.0], [side, side], [0.0, side]], dtype=np.float32
    )
    matrix = cv2.getPerspectiveTransform(corners, destination)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("No se pudo calcular la perspectiva de la ROI")
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError("La perspectiva de la ROI es degenerada") from exc
    if not np.all(np.isfinite(inverse)):
        raise ValueError("La perspectiva de la ROI es degenerada")
    return matrix, inverse, side


def normalize_point(
    cx: float,
    cy: float,
    corners_pixels,
    perspective: bool = False,
    invert_x: bool = False,
    invert_y: bool = False,
) -> tuple[float, float]:
    """
    Pasa un punto de la imagen a [-1, 1] con el origen en el centro de la ROI
    y +Y hacia arriba. Aplica las inversiones de la configuración.
    """
    corners = order_corners(corners_pixels)

    if perspective:
        matrix, _, side = _square_transform(corners)
        point = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, matrix)[0, 0]
        x_norm = (float(transformed[0]) - side / 2.0) / (side / 2.0)
        y_norm = -(float(transformed[1]) - side / 2.0) / (side / 2.0)
    else:
        min_xy = corners.min(axis=0)
        max_xy = corners.max(axis=0)
        center = (min_xy + max_xy) / 2.0
        half = (max_xy - min_xy) / 2.0
        if half[0] <= 0.0 or half[1] <= 0.0:
            raise ValueError("La ROI no tiene ancho y alto válidos")
        x_norm = (float(cx) - float(center[0])) / float(half[0])
        y_norm = -(float(cy) - float(center[1])) / float(half[1])

    if invert_x:
        x_norm = -x_norm
    if invert_y:
        y_norm = -y_norm
    return float(np.clip(x_norm, -1.0, 1.0)), float(np.clip(y_norm, -1.0, 1.0))


def denormalize_point(
    x_norm: float,
    y_norm: float,
    corners_pixels,
    perspective: bool = False,
    invert_x: bool = False,
    invert_y: bool = False,
) -> tuple[float, float]:
    """Inversa de normalize_point, para dibujar el setpoint sobre la imagen."""
    corners = order_corners(corners_pixels)
    x = -float(x_norm) if invert_x else float(x_norm)
    y = -float(y_norm) if invert_y else float(y_norm)

    if perspective:
        _, inverse, side = _square_transform(corners)
        u = (x + 1.0) / 2.0 * side
        v = (-y + 1.0) / 2.0 * side
        point = np.array([[[u, v]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, inverse)[0, 0]
        return float(transformed[0]), float(transformed[1])

    min_xy = corners.min(axis=0)
    max_xy = corners.max(axis=0)
    center = (min_xy + max_xy) / 2.0
    half = (max_xy - min_xy) / 2.0
    px = float(center[0]) + x * float(half[0])
    py = float(center[1]) - y * float(half[1])
    return px, py
