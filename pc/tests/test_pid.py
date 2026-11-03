import pytest
from sim import PIDController


def test_salida_positiva_para_error_positivo():
    pid = PIDController(
        kp=1.0,
        ki=0.0,
        kd=0.0,
        output_limit_deg=8.0,
        slew_rate_dps=1000.0,
        derivative_filter=1.0,
    )
    pid.update(0.0, 0.0, 0.01)
    assert pid.update(1.0, 0.0, 0.01) == pytest.approx(1.0)


def test_respuesta_a_escalon_converge_y_no_se_desborda():
    pid = PIDController(
        kp=4.0,
        ki=0.5,
        kd=1.0,
        output_limit_deg=8.0,
        slew_rate_dps=1000.0,
    )
    # Planta de doble integrador simple para verificar estabilidad básica.
    position = 0.0
    velocity = 0.0
    dt = 0.01
    for _ in range(1500):
        control = pid.update(1.0, position, dt)
        velocity += control * dt
        position += velocity * dt
    assert abs(1.0 - position) < 0.15
    assert abs(pid.last_output) <= 8.0


def test_derivativo_sobre_la_medicion_y_no_sobre_el_error():
    pid = PIDController(
        kp=1.0,
        ki=0.0,
        kd=2.0,
        output_limit_deg=20.0,
        slew_rate_dps=1000.0,
        derivative_filter=1.0,
    )
    pid.update(0.0, 0.0, 0.01)
    after_setpoint_jump = pid.update(1.0, 0.0, 0.01)
    assert pid.derivative_term == pytest.approx(0.0)
    assert after_setpoint_jump == pytest.approx(1.0)

    after_measurement = pid.update(1.0, 0.01, 0.01)
    assert pid.derivative_term < 0.0
    assert after_measurement < after_setpoint_jump


def test_antiwindup_no_acumula_con_salida_saturada():
    pid = PIDController(
        kp=20.0,
        ki=10.0,
        kd=0.0,
        output_limit_deg=8.0,
        slew_rate_dps=1000.0,
        derivative_filter=1.0,
        integral_limit_deg=3.0,
    )
    pid.update(0.0, 0.0, 0.01)
    for _ in range(50):
        pid.update(1.0, 0.0, 0.01)
    assert pid.last_output == pytest.approx(8.0)
    assert pid.integral == pytest.approx(0.0)
    assert pid.update(0.0, 0.1, 0.01) < 0.0


def test_limite_de_integral():
    pid = PIDController(
        kp=0.0,
        ki=100.0,
        kd=0.0,
        output_limit_deg=100.0,
        slew_rate_dps=1000.0,
        derivative_filter=1.0,
        integral_limit_deg=3.0,
    )
    pid.update(0.0, 0.0, 0.01)
    for _ in range(100):
        pid.update(0.1, 0.0, 0.01)
    assert pid.integral == pytest.approx(3.0)


def test_limitador_de_velocidad():
    pid = PIDController(
        kp=100.0,
        ki=0.0,
        kd=0.0,
        output_limit_deg=8.0,
        slew_rate_dps=10.0,
        derivative_filter=1.0,
    )
    pid.update(0.0, 0.0, 0.01)
    assert pid.update(1.0, 0.0, 0.01) == pytest.approx(0.1)
    assert pid.update(1.0, 0.0, 0.01) == pytest.approx(0.2)


def test_dt_invalido_no_cambia_la_salida():
    pid = PIDController(kp=1.0)
    assert pid.update(1.0, 0.0, 0.0) == 0.0
