import math

import pytest
from sim import servo_to_tilt, tilt_to_servo

MECANICA = {
    "center_deg": 90.0,
    "min_deg": 56.0,
    "max_deg": 124.0,
    "l_cm": 8.0,
    "r_cm": 2.0,
}


def test_centro_y_simetria():
    assert tilt_to_servo(0.0, **MECANICA) == pytest.approx(90.0)
    arriba = tilt_to_servo(6.0, **MECANICA)
    abajo = tilt_to_servo(-6.0, **MECANICA)
    assert arriba > 90.0
    assert abajo < 90.0
    assert arriba - 90.0 == pytest.approx(90.0 - abajo)


def test_ida_y_vuelta():
    for tilt in (-8, -6, -3, 0, 3, 6, 8):
        servo = tilt_to_servo(tilt, **MECANICA)
        recovered = servo_to_tilt(servo, **MECANICA)
        assert recovered == pytest.approx(tilt, abs=1e-9)


def test_saturacion_siempre_dentro_de_limites():
    for tilt in range(-30, 31):
        servo = tilt_to_servo(float(tilt), **MECANICA)
        assert 56.0 <= servo <= 124.0
    assert tilt_to_servo(90.0, **MECANICA) == pytest.approx(124.0)
    assert tilt_to_servo(-90.0, **MECANICA) == pytest.approx(56.0)


def test_inversion_y_offset():
    normal = tilt_to_servo(5.0, **MECANICA)
    inverted = tilt_to_servo(5.0, invert=True, **MECANICA)
    assert inverted < 90.0 < normal
    assert 90.0 - inverted == pytest.approx(normal - 90.0)

    shifted = tilt_to_servo(5.0, offset_deg=2.0, **MECANICA)
    assert shifted == pytest.approx(normal + 2.0)

    recovered = servo_to_tilt(
        tilt_to_servo(5.0, invert=True, offset_deg=-3.0, **MECANICA),
        invert=True,
        offset_deg=-3.0,
        **MECANICA,
    )
    assert recovered == pytest.approx(5.0)


def test_formula_coincide_con_la_especificacion():
    tilt = 4.0
    esperado = 90.0 + math.degrees(math.asin(8.0 * math.sin(math.radians(tilt)) / 2.0))
    assert tilt_to_servo(tilt, **MECANICA) == pytest.approx(esperado)


def test_medidas_invalidas():
    with pytest.raises(ValueError):
        tilt_to_servo(0.0, **{**MECANICA, "r_cm": 0.0})
