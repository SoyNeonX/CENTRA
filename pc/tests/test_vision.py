import cv2
import numpy as np
import pytest

from vision import BallDetection, detect_ball

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


@pytest.mark.parametrize("center", [(200, 150), (320, 240), (500, 350)])
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


def test_no_detecta_bloque_cuadrado():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = ORANGE_BGR
    # Un rectángulo naranja grande tiene baja circularidad.
    cv2.rectangle(frame, (100, 100), (400, 300), ORANGE_BGR, -1)
    detection = detect_ball(frame, CONFIG)
    assert not detection.found


def test_detecta_solo_dentro_de_la_placa():
    frame = frame_with_ball(100, 100, radius=18)
    mask = np.zeros((480, 640), dtype=np.uint8)
    cv2.rectangle(mask, (200, 150), (500, 400), 255, -1)
    detection = detect_ball(frame, CONFIG, plate_mask=mask)
    assert not detection.found


def test_mascara_de_tamano_distinto_es_error():
    frame = frame_with_ball()
    mask = np.zeros((10, 10), dtype=np.uint8)
    with pytest.raises(ValueError):
        detect_ball(frame, CONFIG, plate_mask=mask)
