import pytest
from protocol import (
    format_gains,
    format_pose,
    format_telemetry,
    parse_hello,
    parse_host_command,
    parse_telemetry,
)

VALID_TELEMETRY = (
    "T,12345,0.500,-0.250,-0.500,0.250,-4.000,2.000,95.20,87.10,"
    "1.25,-0.50,3"
)


def test_telemetria_valida():
    telemetry = parse_telemetry(VALID_TELEMETRY + "\r\n")
    assert telemetry is not None
    assert telemetry.ms == 12345
    assert telemetry.x == pytest.approx(0.5)
    assert telemetry.servo_y == pytest.approx(87.1)
    assert telemetry.state == 3
    assert telemetry.error_magnitude == pytest.approx(0.559016994)


@pytest.mark.parametrize(
    "line",
    [
        "",
        "basura",
        "OK,P",
        "T,1,2,3",
        "T,1,0,0,0,0,0,0,90,90,0,0",  # truncada
        "T,1,0,0,0,0,0,0,90,90,0,0,9",  # estado inválido
        "T,-1,0,0,0,0,0,0,90,90,0,0,0",  # tiempo negativo
        "T,1,0,0,0,0,0,0,90,90,0,0,x",
        "T,1,nan,0,0,0,0,0,90,90,0,0,0",
    ],
)
def test_telemetria_invalida_no_rompe(line):
    assert parse_telemetry(line) is None


def test_format_pose_satura_y_tres_decimales():
    assert format_pose(2.0, -3.0, True) == "P,1.000,-1.000,1"
    assert format_pose(0.12345, 0.0, False) == "P,0.123,0.000,0"


def test_format_telemetry_tiene_13_campos_y_parsea():
    line = format_telemetry(1, 0.1, 0.2, -0.1, -0.2, 3.0, -4.0, 95, 85, 0, 0, 2)
    assert len(line.split(",")) == 13
    parsed = parse_telemetry(line)
    assert parsed is not None
    assert parsed.state == 2
    assert parsed.tilt_y == pytest.approx(-4.0)


@pytest.mark.parametrize(
    ("line", "command", "args"),
    [
        ("P,0.250,-0.500,1", "P", (0.25, -0.5, 1)),
        ("M,2", "M", (2,)),
        ("A,-3.50,4.00", "A", (-3.5, 4.0)),
        ("V,90,100", "V", (90.0, 100.0)),
        ("G,B,6,0.2,4", "G", ("B", 6.0, 0.2, 4.0)),
        ("S,0,0.5", "S", (0.0, 0.5)),
        ("C,1.5,-2", "C", (1.5, -2.0)),
        ("L,7.5", "L", (7.5,)),
        ("W", "W", ()),
        ("H\r\n", "H", ()),
    ],
)
def test_parsea_comandos_validos(line, command, args):
    parsed = parse_host_command(line)
    assert parsed is not None
    assert parsed[0] == command
    assert len(parsed[1]) == len(args)
    for actual, expected in zip(parsed[1], args):
        if isinstance(expected, str):
            assert actual == expected
        else:
            assert actual == pytest.approx(expected)


def test_comandos_validos_con_tipos_simples():
    assert parse_host_command("M,1") == ("M", (1,))
    assert parse_host_command("W") == ("W", ())
    assert parse_host_command("G,X,1,2,3") == ("G", ("X", 1.0, 2.0, 3.0))


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "P,0.1,0.2",  # truncado
        "P,0.1,0.2,2",  # found inválido
        "P,a,0.2,1",
        "M,3",
        "M,1,2",
        "G,Z,1,2,3",
        "G,B,1,2",
        "A,1,nan",
        "L,abc",
        "W,1",
        "basura",
        "P,1,2,1,5",
    ],
)
def test_comandos_invalidos_no_rompen(line):
    assert parse_host_command(line) is None


def test_hello():
    assert parse_hello("HELLO,1.0.0\r\n") == "1.0.0"
    assert parse_hello("HELLO,") is None
    assert parse_hello("OK,H") is None


def test_format_gains_valida_eje():
    assert format_gains("b", 6, 0.2, 4) == "G,B,6.000,0.200,4.000"
    with pytest.raises(ValueError):
        format_gains("Q", 1, 2, 3)
