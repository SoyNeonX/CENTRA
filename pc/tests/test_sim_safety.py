"""Comportamiento de seguridad del FakeESP32 y del registro CSV."""

import csv

import pytest
from config import load_config
from logger import TelemetryLogger
from protocol import parse_telemetry
from sim import FakeESP32


@pytest.fixture()
def config():
    return load_config()


def test_fake_no_entra_en_automatico_sin_m2(config):
    fake = FakeESP32(config)
    for _ in range(30):
        fake.receive("P,0.300,0.100,1")
        fake.control_tick()
    assert fake.mode == 0
    assert fake.tilt_x == pytest.approx(0.0, abs=1e-6)
    assert fake.tilt_y == pytest.approx(0.0, abs=1e-6)


def test_fake_arranca_buscando_y_luego_estabiliza(config):
    fake = FakeESP32(config)
    fake.receive("M,2")
    fake.receive("P,0.300,0.100,1")
    fake.control_tick()
    fake.control_tick()
    assert fake.mode == 2
    assert fake.auto_phase == 3
    assert fake._state_code() == 3


def test_fake_pierde_pelota_y_nivela(config):
    fake = FakeESP32(config)
    fake.receive("M,2")
    for _ in range(10):
        fake.receive("P,0.500,0.000,1")
        fake.control_tick()
    fake.receive("A,0,0")  # rechazado en automático, no debe romper
    fake.control_tick()
    # Se dejan de mandar P: pasados 200 ms debe quedar perdida.
    for _ in range(30):
        fake.control_tick()
    assert fake.mode == 2
    assert fake.auto_phase == 4
    assert abs(fake.tilt_x) < 0.2
    assert abs(fake.tilt_y) < 0.2


def test_fake_respeta_limites_de_servo(config):
    fake = FakeESP32(config)
    fake.receive("M,1")
    fake.receive("A,-8,8")
    for _ in range(300):
        fake.control_tick()
    assert 56.0 <= fake.servo_x <= 124.0
    assert 56.0 <= fake.servo_y <= 124.0
    # El ángulo de servo no debe ir más allá del límite de inclinación.
    assert abs(fake.tilt_x) <= 8.0
    assert abs(fake.tilt_y) <= 8.0


def test_telemetria_del_fake_se_parsea(config):
    fake = FakeESP32(config)
    fake.receive("M,2")
    fake.receive("P,0.100,0.200,1")
    lines = []
    for _ in range(4):
        lines.extend(fake.control_tick())
    assert lines
    telemetry = parse_telemetry(lines[-1])
    assert telemetry is not None
    assert telemetry.state == 3
    assert telemetry.x == pytest.approx(0.1)


def test_logger_guarda_csv(tmp_path):
    fake = FakeESP32(load_config())
    fake.receive("M,2")
    fake.receive("P,0.100,0.200,1")
    fake.control_tick()
    # Asegura al menos una T.
    lines = []
    for _ in range(5):
        lines.extend(fake.control_tick())
    telemetry = parse_telemetry(lines[-1])
    assert telemetry is not None

    logger = TelemetryLogger(tmp_path, enabled=True)
    logger.log(telemetry)
    logger.close()

    assert logger.path is not None
    with logger.path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert float(rows[0]["x"]) == pytest.approx(0.1)
    assert int(rows[0]["estado"]) == 3
