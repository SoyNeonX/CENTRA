"""
Detección de los marcadores ArUco que definen la placa y conversión a cm.

La cámara mira la placa desde arriba. Los marcadores están en las cuatro
esquinas, con orden fijo visto desde la cámara:

    ID 0: arriba-izquierda    ID 1: arriba-derecha
    ID 2: abajo-derecha       ID 3: abajo-izquierda

El sistema de coordenadas de la placa tiene origen en el centro, +X a la
derecha y +Y hacia arriba (como en la imagen), medido en centímetros.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

# Valores por defecto para dibujar/validar; los valores reales salen de config.
REQUIRED_IDS = (0, 1, 2, 3)


@dataclass(frozen=True)
class PlatePose:
    """Pose de la placa en un cuadro.

    `valid=True` significa que hay una homografía utilizable, aunque sea la
    última pose guardada (`stale=True`). El control no debe usar una pose
    vencida; el pipeline de visión la puede conservar hasta 0.5 s.
    """

    valid: bool
    stale: bool
    homography: np.ndarray | None
    inverse_homography: np.ndarray | None
    plate_corners_px: np.ndarray | None
    marker_centers_px: dict | None
    detected_ids: tuple
    timestamp_s: float

    @classmethod
    def invalid(cls, timestamp_s: float, detected_ids=()) -> "PlatePose":
        return cls(
            valid=False,
            stale=False,
            homography=None,
            inverse_homography=None,
            plate_corners_px=None,
            marker_centers_px=None,
            detected_ids=tuple(detected_ids),
            timestamp_s=timestamp_s,
        )

    def pixel_to_cm(self, px: float, py: float) -> tuple[float, float] | None:
        if not self.valid or self.homography is None:
            return None
        point = np.array([[[float(px), float(py)]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.homography)[0, 0]
        return float(transformed[0]), float(transformed[1])

    def cm_to_pixel(self, x_cm: float, y_cm: float) -> tuple[float, float] | None:
        if not self.valid or self.inverse_homography is None:
            return None
        point = np.array([[[float(x_cm), float(y_cm)]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.inverse_homography)[0, 0]
        return float(transformed[0]), float(transformed[1])

    def plate_mask(self, frame_shape) -> np.ndarray | None:
        if not self.valid or self.plate_corners_px is None:
            return None
        height, width = frame_shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        polygon = np.asarray(self.plate_corners_px, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [polygon], 255)
        return mask

    def contains_pixel(self, px: float, py: float) -> bool:
        if not self.valid or self.plate_corners_px is None:
            return False
        polygon = np.asarray(self.plate_corners_px, dtype=np.float32)
        return cv2.pointPolygonTest(polygon, (float(px), float(py)), False) >= 0

    def marker_count(self) -> int:
        return len(self.detected_ids)


class MarkerTracker:
    """Detecta ArUco, calcula la homografía y conserva la última pose 0.5 s."""

    def __init__(self, config: dict):
        plate = config["plate"]
        self.plate_config = plate
        self.size_cm = float(plate["size_cm"])
        self.marker_size_cm = float(plate.get("marker_size_cm", 4.0))
        self.lost_timeout_s = float(plate.get("lost_timeout_s", 0.5))
        self.marker_ids = tuple(int(value) for value in plate["marker_ids"])
        self.marker_centers_cm = {
            int(marker_id): (float(point[0]), float(point[1]))
            for marker_id, point in zip(
                self.marker_ids, plate["marker_centers_cm"]
            )
        }
        self.half_size_cm = self.size_cm / 2.0
        self.last_pose: PlatePose | None = None

        dictionary_name = str(
            plate.get("marker_dictionary", "DICT_4X4_50")
        )
        dictionary_id = getattr(cv2.aruco, dictionary_name, None)
        if dictionary_id is None:
            raise ValueError(f"Diccionario ArUco desconocido: {dictionary_name}")
        self.dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
        try:
            parameters = cv2.aruco.DetectorParameters()
            parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            self.detector = cv2.aruco.ArucoDetector(self.dictionary, parameters)
        except AttributeError:
            self.detector = None
            self.parameters = cv2.aruco.DetectorParameters()

    def _detect_markers(self, frame):
        if self.detector is not None:
            corners, ids, _ = self.detector.detectMarkers(frame)
        else:  # OpenCV 4.7/4.8 con API anterior
            corners, ids, _ = cv2.aruco.detectMarkers(
                frame, self.dictionary, parameters=self.parameters
            )
        return corners, ids

    def _build_pose(self, corners, ids, now_s: float) -> PlatePose:
        found = {}
        if ids is not None:
            for marker_id, marker_corners in zip(ids.flatten(), corners):
                marker_id = int(marker_id)
                if marker_id not in self.marker_centers_cm:
                    continue
                points = np.asarray(marker_corners, dtype=np.float32).reshape(4, 2)
                found[marker_id] = (
                    float(points[:, 0].mean()),
                    float(points[:, 1].mean()),
                )

        detected_ids = tuple(sorted(found.keys()))
        if len(found) != 4:
            if (
                self.last_pose is not None
                and now_s - self.last_pose.timestamp_s <= self.lost_timeout_s
            ):
                previous = self.last_pose
                return PlatePose(
                    valid=True,
                    stale=True,
                    homography=previous.homography,
                    inverse_homography=previous.inverse_homography,
                    plate_corners_px=previous.plate_corners_px,
                    marker_centers_px=previous.marker_centers_px,
                    detected_ids=detected_ids,
                    timestamp_s=previous.timestamp_s,
                )
            return PlatePose.invalid(now_s, detected_ids)

        image_points = []
        plate_points = []
        for marker_id in self.marker_ids:
            image_points.append(found[marker_id])
            plate_points.append(self.marker_centers_cm[marker_id])
        image_points = np.asarray(image_points, dtype=np.float32)
        plate_points = np.asarray(plate_points, dtype=np.float32)

        try:
            homography = cv2.getPerspectiveTransform(image_points, plate_points)
            inverse = np.linalg.inv(homography)
        except (cv2.error, np.linalg.LinAlgError):
            return PlatePose.invalid(now_s, detected_ids)
        if not np.all(np.isfinite(homography)) or not np.all(np.isfinite(inverse)):
            return PlatePose.invalid(now_s, detected_ids)

        # Verificación de ida y vuelta: evita poses absurdas por marcadores
        # mal identificados.
        back = cv2.perspectiveTransform(
            image_points.reshape(-1, 1, 2), homography
        ).reshape(-1, 2)
        if float(np.max(np.linalg.norm(back - plate_points, axis=1))) > 1e-3:
            return PlatePose.invalid(now_s, detected_ids)

        half = self.half_size_cm
        plate_corners_cm = np.array(
            [[-half, half], [half, half], [half, -half], [-half, -half]],
            dtype=np.float32,
        )
        plate_corners_px = cv2.perspectiveTransform(
            plate_corners_cm.reshape(-1, 1, 2), inverse
        ).reshape(-1, 2)

        pose = PlatePose(
            valid=True,
            stale=False,
            homography=homography,
            inverse_homography=inverse,
            plate_corners_px=plate_corners_px,
            marker_centers_px=found,
            detected_ids=detected_ids,
            timestamp_s=now_s,
        )
        self.last_pose = pose
        return pose

    def detect(self, frame, now_s: float | None = None) -> PlatePose:
        if frame is None or getattr(frame, "size", 0) == 0:
            now_s = time.monotonic() if now_s is None else float(now_s)
            return PlatePose.invalid(now_s)
        now_s = time.monotonic() if now_s is None else float(now_s)
        try:
            corners, ids = self._detect_markers(frame)
        except cv2.error:
            return PlatePose.invalid(now_s)
        return self._build_pose(corners, ids, now_s)


def _marker_dictionary(config: dict):
    plate = config["plate"]
    dictionary_id = getattr(
        cv2.aruco, str(plate.get("marker_dictionary", "DICT_4X4_50")), None
    )
    if dictionary_id is None:
        raise ValueError("Diccionario ArUco desconocido")
    return cv2.aruco.getPredefinedDictionary(dictionary_id)


def _generate_marker_image(dictionary, marker_id: int, side_px: int) -> np.ndarray:
    if hasattr(cv2.aruco, "generateImageMarker"):
        return cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)
    return cv2.aruco.drawMarker(dictionary, marker_id, side_px)


def draw_markers(
    frame,
    plate_to_image: np.ndarray,
    config: dict,
    source_corners_by_id: dict | None = None,
) -> None:
    """
    Dibuja los 4 marcadores sobre una superficie plana usando la homografía
    `plate_to_image` que va de cm de la placa a píxeles.

    Se usa en tests y en la cámara sintética. `source_corners_by_id` permite
    indicar las cuatro esquinas físicas de cada marcador; si no, se calculan
    alrededor de `marker_centers_cm`.
    """
    plate = config["plate"]
    dictionary = _marker_dictionary(config)
    size_cm = float(plate["marker_size_cm"])
    marker_centers = plate["marker_centers_cm"]
    marker_ids = [int(value) for value in plate["marker_ids"]]

    side_px = 100
    for index, marker_id in enumerate(marker_ids):
        if source_corners_by_id is not None and marker_id in source_corners_by_id:
            source = np.asarray(
                source_corners_by_id[marker_id], dtype=np.float32
            )
        else:
            cx, cy = marker_centers[index]
            source = np.array(
                [
                    [cx - size_cm / 2.0, cy + size_cm / 2.0],
                    [cx + size_cm / 2.0, cy + size_cm / 2.0],
                    [cx + size_cm / 2.0, cy - size_cm / 2.0],
                    [cx - size_cm / 2.0, cy - size_cm / 2.0],
                ],
                dtype=np.float32,
            )

        destination = cv2.perspectiveTransform(
            source.reshape(-1, 1, 2), plate_to_image
        ).reshape(-1, 2)

        marker_image = _generate_marker_image(dictionary, marker_id, side_px)
        marker_image = np.pad(marker_image, 8, constant_values=255)
        # Fondo blanco de separación, como suele recomendarse para ArUco.
        marker_rgb = cv2.cvtColor(marker_image, cv2.COLOR_GRAY2BGR)
        src = np.array(
            [
                [0, 0],
                [side_px, 0],
                [side_px, side_px],
                [0, side_px],
            ],
            dtype=np.float32,
        )
        # El blanco de padding debe quedar dentro de la máscara; para la
        # transformación usamos solo el cuadrado interno del marcador.
        src_inner = src + 8.0
        matrix = cv2.getPerspectiveTransform(src_inner, destination)
        warped = cv2.warpPerspective(
            marker_rgb,
            matrix,
            (frame.shape[1], frame.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_TRANSPARENT,
        )
        mask = cv2.warpPerspective(
            np.full(marker_rgb.shape[:2], 255, dtype=np.uint8),
            matrix,
            (frame.shape[1], frame.shape[0]),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        cv2.copyTo(warped, mask, frame)
