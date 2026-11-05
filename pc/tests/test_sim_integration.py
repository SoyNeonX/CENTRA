"""
Prueba de integración cerrada con cámara sintética, ArUco y FakeESP32.

La meta es |error| < 0.5 cm en ambos ejes. Se prueba el caso normal y el caso
con inversión de software en X e Y (la PC espeja P y S).
"""

import copy

import pytest
from config import load_config
from markers import MarkerTracker
from protocol import format_pose
from sim import Simulation
from vision import detect_ball

FPS = 60.0
DT = 1.0 / FPS
MAX_TIME_S = 12.0
TOLERANCE = 0.5
STABLE_TIME_S = 1.0


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.mark.parametrize("inverted", [False, True])
def test_la_pelota_converge_al_centro_en_simulacion(config, inverted):
    test_config = copy.deepcopy(config)
    if inverted:
        test_config["control"]["invert_x"] = True
        test_config["control"]["invert_y"] = True
        test_config["simulation"]["servo"]["invert_x"] = True
        test_config["simulation"]["servo"]["invert_y"] = True

    sim = Simulation(test_config)
    sim.start()
    sim.link.send("M,2")
    tracker = MarkerTracker(test_config)
    sign = -1.0 if inverted else 1.0

    converged_at = None
    stable_since = None
    telemetry = None
    steps = int(MAX_TIME_S * FPS)

    for step in range(steps):
        frame = sim.render_frame()
        pose = tracker.detect(frame)
        detection = None
        ball_cm = None
        if pose.valid:
            mask = pose.plate_mask(frame.shape)
            detection = detect_ball(frame, test_config["vision"], plate_mask=mask)
            if detection.found:
                ball_cm = pose.pixel_to_cm(detection.cx, detection.cy)

        if ball_cm is None:
            sim.link.send(format_pose(0.0, 0.0, False))
        else:
            sim.link.send(format_pose(ball_cm[0] * sign, ball_cm[1] * sign, True))

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
        f"no convergió (invertido={inverted}): "
        f"x={sim.ball_x:.3f} cm, y={sim.ball_y:.3f} cm, "
        f"tilt=({sim.fake.tilt_x:.2f},{sim.fake.tilt_y:.2f})"
    )
    assert converged_at < MAX_TIME_S
    assert telemetry is not None
    assert abs(sim.ball_x) < TOLERANCE
    assert abs(sim.ball_y) < TOLERANCE

    # Esta prueba no valida las ganancias reales; solo la lógica del lazo.
    print(
        f"\nConvergencia simulada (invertido={inverted}): "
        f"{converged_at:.2f} s"
    )
