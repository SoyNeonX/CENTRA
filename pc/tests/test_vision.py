import cv2
import numpy as np
import pytest
from vision import (
    BallDetection,
    build_roi_mask,
    corners_to_pixels,
    denormalize_point,
    detect_ball,
    normalize_point,
    order_corners,
    pixels_to_normalized_corners,
)

CONFIG = {
    "hsv_lower": [5, 120, 120],
    "hsv_upper": [20, 255, 255],
    "blur_kernel": 5,
    "morph_kernel": 5,
    "min_area": 150,
    "max_area": 12000,
    "min_circularity": 0.55,
}

ORANGE_BGR = (0, 140, 255)
BLUE_BGR = (180, 80, 0)


def frame_with_ball(cx=320, cy=240, radius=18, brightness=1.0, noise=0.0):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = BLUE_BGR
    cv2.circle(frame, (cx, cy), radius, ORANGE_BGR, thickness=-1, lineType=cv2.LINE_AA)
    if brightness != 1.0:
        frame = np.clip(frame.astype(np.float32) * brightness, 0, 255).astype(np.uint8)
    if noise > 0:
        rng = np.random.default_rng(1234)
        noisy = frame.astype(np.float32) + rng.normal(0, noise, frame.shape)
        frame = np.clip(noisy, 0, 255).astype(np.uint8)
    return frame


@pytest.mark.parametrize(
    "center",
    [(200, 150), (320, 240), (500, 350)],
)
def test_detecta_centro_con_error_menor_a_dos_pixeles(center):
    frame = frame_with_ball(*center, radius=20)
    detection = detect_ball(frame, CONFIG)
    assert detection.found
    assert abs(detection.cx - center[0]) < 2.0
    assert abs(detection.cy - center[1]) < 2.0
    assert abs(detection.radius - 20) < 2.0


def test_sin_pelota_devuelve_found_false():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = BLUE_BGR
    detection = detect_ball(frame, CONFIG)
    assert detection == BallDetection(0.0, 0.0, 0.0, False)
    assert detection.found is False


def test_detecta_con_ruido_y_cambio_de_brillo():
    frame = frame_with_ball(410, 190, radius=16, brightness=1.15, noise=10.0)
    detection = detect_ball(frame, CONFIG)
    assert detection.found
    assert abs(detection.cx - 410) < 2.0
    assert abs(detection.cy - 190) < 2.0


def test_no_detecta_color_azul_ni_bloque_cuadrado():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = ORANGE_BGR
    # Un rectángulo naranja grande tiene baja circularidad.
    cv2.rectangle(frame, (100, 100), (400, 300), ORANGE_BGR, -1)
    detection = detect_ball(frame, CONFIG)
    assert not detection.found


def test_detecta_solo_dentro_de_la_roi():
    frame = frame_with_ball(100, 100, radius=18)
    corners = np.array([[200, 150], [500, 150], [500, 400], [200, 400]], dtype=np.float32)
    mask = build_roi_mask(frame.shape, corners)
    detection = detect_ball(frame, CONFIG, roi_mask=mask)
    assert not detection.found


def test_roi_ordenada_y_normalizacion():
    corners = np.array([[100, 50], [500, 50], [500, 450], [100, 450]], dtype=np.float32)
    center = normalize_point(300, 250, corners)
    assert center == pytest.approx((0.0, 0.0))
    assert normalize_point(500, 250, corners)[0] == pytest.approx(1.0)
    assert normalize_point(300, 50, corners)[1] == pytest.approx(1.0)
    assert normalize_point(100, 450, corners) == pytest.approx((-1.0, -1.0))


def test_normalizacion_aplica_inversiones():
    corners = np.array([[100, 50], [500, 50], [500, 450], [100, 450]], dtype=np.float32)
    x, y = normalize_point(400, 100, corners, invert_x=True, invert_y=True)
    assert x < 0
    assert y < 0


def test_perspectiva_mapea_las_cuatro_esquinas():
    corners = np.array([[120, 60], [520, 100], [470, 430], [80, 390]], dtype=np.float32)
    expected = [(-1, 1), (1, 1), (1, -1), (-1, -1)]
    for point, target in zip(corners, expected):
        x, y = normalize_point(point[0], point[1], corners, perspective=True)
        assert x == pytest.approx(target[0], abs=1e-3)
        assert y == pytest.approx(target[1], abs=1e-3)


def test_ida_y_vuelta_normalizacion():
    corners = np.array([[90, 70], [530, 80], [480, 420], [110, 400]], dtype=np.float32)
    for nx, ny in [(0, 0), (0.5, -0.3), (-0.8, 0.7)]:
        px, py = denormalize_point(nx, ny, corners, perspective=True)
        rx, ry = normalize_point(px, py, corners, perspective=True)
        assert rx == pytest.approx(nx, abs=1e-3)
        assert ry == pytest.approx(ny, abs=1e-3)


def test_ordenar_esquinas_desordenadas():
    points = np.array([[500, 450], [100, 50], [100, 450], [500, 50]], dtype=np.float32)
    ordered = order_corners(points)
    assert ordered.tolist() == [[100, 50], [500, 50], [500, 450], [100, 450]]


def test_esquinas_pixeles_a_normalizado_y_roi_pixeles():
    points = np.array([[64, 48], [576, 48], [576, 432], [64, 432]], dtype=np.float32)
    normalized = pixels_to_normalized_corners(points, 640, 480)
    back = corners_to_pixels(normalized, 640, 480)
    assert np.allclose(back, points)
