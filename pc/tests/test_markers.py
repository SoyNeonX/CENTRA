import cv2
import numpy as np
import pytest

from config import load_config
from markers import MarkerTracker, draw_markers


def make_plate_scene(config, image_corners=None, draw=True):
    """Crea una imagen con una placa oscura y los 4 ArUco en perspectiva."""
    frame = np.full((480, 640, 3), (150, 70, 20), dtype=np.uint8)
    if image_corners is None:
        image_corners = np.array(
            [[70, 50], [560, 70], [590, 430], [50, 410]], dtype=np.float32
        )
    half = float(config["plate"]["size_cm"]) / 2.0
    plate_cm = np.array(
        [[-half, half], [half, half], [half, -half], [-half, -half]],
        dtype=np.float32,
    )
    image_corners = np.asarray(image_corners, dtype=np.float32)
    plate_to_image = cv2.getPerspectiveTransform(plate_cm, image_corners)
    cv2.fillPoly(frame, [image_corners.astype(np.int32)], (35, 35, 35))
    cv2.polylines(frame, [image_corners.astype(np.int32)], True, (180, 180, 180), 2)
    if draw:
        draw_markers(frame, plate_to_image, config)
    return frame, plate_to_image


def project_plate_to_image(plate_to_image, x_cm, y_cm):
    point = np.array([[[float(x_cm), float(y_cm)]]], dtype=np.float32)
    return cv2.perspectiveTransform(point, plate_to_image)[0, 0]


def test_detecta_los_cuatro_marcadores_y_homografia(config=None):
    config = load_config()
    frame, plate_to_image = make_plate_scene(config)
    tracker = MarkerTracker(config)
    pose = tracker.detect(frame, now_s=10.0)

    assert pose.valid
    assert not pose.stale
    assert set(pose.detected_ids) == {0, 1, 2, 3}
    assert pose.marker_count() == 4

    # Probar puntos dentro de la placa. El error de ida y vuelta debe ser
    # menor a 0.2 cm.
    for x_cm, y_cm in [(0, 0), (8, -6), (-9, 7), (4.5, 2.5)]:
        px, py = project_plate_to_image(plate_to_image, x_cm, y_cm)
        recovered = pose.pixel_to_cm(px, py)
        assert recovered is not None
        assert abs(recovered[0] - x_cm) < 0.2
        assert abs(recovered[1] - y_cm) < 0.2

    center = pose.cm_to_pixel(0, 0)
    assert center is not None
    assert abs(center[0] - 320) < 25
    assert abs(center[1] - 240) < 25


def test_mascara_solo_dentro_de_la_placa():
    config = load_config()
    frame, _ = make_plate_scene(config)
    pose = MarkerTracker(config).detect(frame, now_s=1.0)
    assert pose.valid
    mask = pose.plate_mask(frame.shape)
    assert mask is not None
    assert mask[240, 320] == 255
    assert mask[5, 5] == 0
    assert pose.contains_pixel(320, 240)
    assert not pose.contains_pixel(2, 2)


def test_pose_se_conserva_medio_segundo_sin_marcadores():
    config = load_config()
    frame, _ = make_plate_scene(config)
    tracker = MarkerTracker(config)
    valid = tracker.detect(frame, now_s=100.0)
    assert valid.valid

    blank = np.zeros_like(frame)
    stale = tracker.detect(blank, now_s=100.3)
    assert stale.valid
    assert stale.stale
    assert stale.homography is not None

    expired = tracker.detect(blank, now_s=100.7)
    assert not expired.valid


def test_marcadores_incompletos_reportan_ids_y_no_crean_pose():
    config = load_config()
    frame, _ = make_plate_scene(config)
    # Ocultar un marcador (la esquina superior izquierda).
    frame[40:170, 40:220] = (20, 20, 20)
    tracker = MarkerTracker(config)
    pose = tracker.detect(frame, now_s=1.0)
    assert not pose.valid
    assert 0 not in pose.detected_ids


def test_perspectiva_y_error_menor_a_dos_decimas():
    config = load_config()
    corners = np.array(
        [[120, 100], [530, 40], [600, 450], [40, 400]], dtype=np.float32
    )
    frame, plate_to_image = make_plate_scene(config, image_corners=corners)
    pose = MarkerTracker(config).detect(frame, now_s=5.0)
    assert pose.valid
    assert set(pose.detected_ids) == {0, 1, 2, 3}

    for x_cm, y_cm in [(-10, 10), (10, 10), (10, -10), (-10, -10)]:
        px, py = project_plate_to_image(plate_to_image, x_cm, y_cm)
        x_back, y_back = pose.pixel_to_cm(px, py)
        assert abs(x_back - x_cm) < 0.2
        assert abs(y_back - y_cm) < 0.2


def test_placa_no_detectada_desde_el_principio():
    config = load_config()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pose = MarkerTracker(config).detect(frame, now_s=1.0)
    assert not pose.valid
    assert not pose.stale
    assert pose.plate_mask(frame.shape) is None
    assert pose.pixel_to_cm(100, 100) is None


def test_configuracion_de_marcadores_invalida():
    config = load_config()
    config["plate"]["marker_dictionary"] = "NO_EXISTE"
    with pytest.raises(ValueError):
        MarkerTracker(config)
