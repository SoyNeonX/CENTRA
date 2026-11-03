"""
Prueba de integración cerrada con cámara sintética y FakeESP32.

La meta es |error| < 0.05 en ambos ejes. El tiempo de convergencia se mide y
se exige que sea menor a 12 s (la simulación corre a 60 fps).
"""

import pytest
from config import load_config
from protocol import format_pose
from sim import Simulation
from vision import (
    build_roi_mask,
    corners_to_pixels,
    detect_ball,
    normalize_point,
)

FPS = 60.0
DT = 1.0 / FPS
MAX_TIME_S = 15.0
TOLERANCE = 0.05
STABLE_TIME_S = 1.0


@pytest.fixture(scope="module")
def config():
    return load_config()


def test_la_pelota_converge_al_centro_en_simulacion(config):
    sim = Simulation(config)
    sim.start()
    sim.link.send("M,2")

    width = config["camera"]["width"]
    height = config["camera"]["height"]
    corners = corners_to_pixels(
        config["roi"]["corners_normalized"], width, height
    )
    mask = build_roi_mask((height, width, 3), corners)
    perspective = bool(config["roi"].get("perspective", False))
    invert_x = bool(config["control"].get("invert_x", False))
    invert_y = bool(config["control"].get("invert_y", False))

    converged_at = None
    stable_since = None
    telemetry = None
    steps = int(MAX_TIME_S * FPS)

    for step in range(steps):
        frame = sim.render_frame()
        detection = detect_ball(frame, config["vision"], roi_mask=mask)
        if detection.found:
            nx, ny = normalize_point(
                detection.cx,
                detection.cy,
                corners,
                perspective=perspective,
                invert_x=invert_x,
                invert_y=invert_y,
            )
        else:
            nx, ny = 0.0, 0.0
        sim.link.send(format_pose(nx, ny, detection.found))
        sim.advance(DT)

        telemetry = sim.link.latest_telemetry()
        error_x = abs(sim.ball_x - sim.fake.setpoint_x)
        error_y = abs(sim.ball_y - sim.fake.setpoint_y)
        now = (step + 1) * DT
        if error_x < TOLERANCE and error_y < TOLERANCE:
            if stable_since is None:
                stable_since = now
            if now - stable_since >= STABLE_TIME_S:
                converged_at = stable_since
                break
        else:
            stable_since = None

    assert converged_at is not None, (
        f"no convergió: x={sim.ball_x:.3f}, y={sim.ball_y:.3f}, "
        f"tilt=({sim.fake.tilt_x:.2f},{sim.fake.tilt_y:.2f})"
    )
    assert converged_at < 12.0
    assert telemetry is not None
    assert abs(sim.ball_x) < TOLERANCE
    assert abs(sim.ball_y) < TOLERANCE

    # Esta prueba no valida las ganancias reales; solo la lógica del lazo.
    print(f"\nConvergencia simulada: {converged_at:.2f} s")
