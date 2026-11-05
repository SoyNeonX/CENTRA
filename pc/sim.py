"""
Simulación completa sin hardware.

Incluye:
- Un PID en Python equivalente al del firmware.
- La conversión inclinación <-> servo con los mismos límites y signos.
- Un FakeESP32 que recibe y responde exactamente el mismo protocolo de texto.
- Una cámara sintética con una pelota naranja sobre fondo azul.
- Física simple de una pelota sobre una placa inclinada.

Esto valida la lógica, el protocolo y la integración. NO reemplaza el ajuste
real de ganancias ni valida servos, cámara, luz o mecánica.
"""

from __future__ import annotations

import math
import time
from collections import deque

import cv2
import numpy as np
from markers import draw_markers
from protocol import format_telemetry, parse_host_command, parse_telemetry

FW_VERSION_SIM = "1.1.0-sim"

# Límites de ganancias equivalentes a config.h (grados por cm).
GAIN_LIMITS = {
    "kp": (0.0, 5.0),
    "ki": (0.0, 1.0),
    "kd": (0.0, 5.0),
}



def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


# --------------------------------------------------------------------- PID ---


class PIDController:
    """Copia didáctica del pid.cpp del ESP32, para el FakeESP32 y los tests."""

    def __init__(
        self,
        kp: float = 0.0,
        ki: float = 0.0,
        kd: float = 0.0,
        output_limit_deg: float = 8.0,
        slew_rate_dps: float = 120.0,
        derivative_filter: float = 0.15,
        integral_limit_deg: float = 3.0,
    ):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.output_limit_deg = abs(float(output_limit_deg))
        self.slew_rate_dps = abs(float(slew_rate_dps))
        self.derivative_filter = clamp(derivative_filter, 0.0, 1.0)
        self.integral_limit_deg = abs(float(integral_limit_deg))
        self.reset()

    def reset(self) -> None:
        self.integral = 0.0
        self.filtered_derivative = 0.0
        self.derivative_term = 0.0
        self.last_measurement = 0.0
        self.last_output = 0.0
        self.initialized = False

    def set_gains(self, kp: float, ki: float, kd: float) -> None:
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)

    def set_output_limit(self, limit_deg: float) -> None:
        self.output_limit_deg = abs(float(limit_deg))

    def set_slew_rate(self, rate_dps: float) -> None:
        self.slew_rate_dps = abs(float(rate_dps))

    def update(self, setpoint: float, measurement: float, dt_s: float) -> float:
        if not dt_s > 0.0:
            return self.last_output
        dt_s = min(float(dt_s), 0.05)
        error = float(setpoint) - float(measurement)

        if self.initialized:
            raw_derivative = (measurement - self.last_measurement) / dt_s
        else:
            raw_derivative = 0.0
        self.filtered_derivative += self.derivative_filter * (
            raw_derivative - self.filtered_derivative
        )
        self.derivative_term = -self.kd * self.filtered_derivative

        tentative_integral = self.integral + self.ki * error * dt_s
        tentative_integral = clamp(
            tentative_integral,
            -self.integral_limit_deg,
            self.integral_limit_deg,
        )
        unsaturated = self.kp * error + tentative_integral + self.derivative_term

        # Anti-windup: no acumular si la salida está saturada y el error empuja
        # todavía más en ese sentido.
        pushes_positive = unsaturated > self.output_limit_deg and error > 0.0
        pushes_negative = unsaturated < -self.output_limit_deg and error < 0.0
        if pushes_positive or pushes_negative:
            tentative_integral = self.integral
            unsaturated = (
                self.kp * error + tentative_integral + self.derivative_term
            )

        self.integral = tentative_integral
        limited = clamp(
            unsaturated, -self.output_limit_deg, self.output_limit_deg
        )
        max_step = self.slew_rate_dps * dt_s
        self.last_output += clamp(
            limited - self.last_output, -max_step, max_step
        )
        self.last_output = clamp(
            self.last_output, -self.output_limit_deg, self.output_limit_deg
        )
        self.last_measurement = float(measurement)
        self.initialized = True
        return self.last_output


# ---------------------------------------------------- mecánica de los servos ---


def tilt_to_servo(
    tilt_deg: float,
    *,
    center_deg: float,
    min_deg: float,
    max_deg: float,
    l_cm: float,
    r_cm: float,
    invert: bool = False,
    offset_deg: float = 0.0,
) -> float:
    """
    servo_deg = centro + offset + signo * degrees(asin(L*sin(tilt)/r))

    El resultado siempre queda dentro de [min_deg, max_deg].
    """
    if r_cm <= 0.0 or l_cm < 0.0:
        raise ValueError("Las medidas de la mecánica deben ser positivas")
    ratio = clamp(l_cm * math.sin(math.radians(tilt_deg)) / r_cm, -1.0, 1.0)
    delta_deg = math.degrees(math.asin(ratio))
    sign = -1.0 if invert else 1.0
    angle = center_deg + offset_deg + sign * delta_deg
    return clamp(angle, min_deg, max_deg)


def servo_to_tilt(
    servo_deg: float,
    *,
    center_deg: float,
    min_deg: float,
    max_deg: float,
    l_cm: float,
    r_cm: float,
    invert: bool = False,
    offset_deg: float = 0.0,
) -> float:
    """Inversa de tilt_to_servo, útil para saber la inclinación real de la placa."""
    if r_cm <= 0.0 or l_cm <= 0.0:
        raise ValueError("Las medidas de la mecánica deben ser positivas")
    angle = clamp(servo_deg, min_deg, max_deg)
    sign = -1.0 if invert else 1.0
    beta_deg = sign * (angle - center_deg - offset_deg)
    ratio = clamp(r_cm * math.sin(math.radians(beta_deg)) / l_cm, -1.0, 1.0)
    return math.degrees(math.asin(ratio))


def _servo_axis(servo_config: dict, axis: str) -> dict:
    axis = axis.lower()
    if axis not in ("x", "y"):
        raise ValueError("axis debe ser 'x' o 'y'")
    return {
        "center_deg": float(servo_config["center_deg"]),
        "min_deg": float(servo_config["min_deg"]),
        "max_deg": float(servo_config["max_deg"]),
        "l_cm": float(servo_config["l_cm"]),
        "r_cm": float(servo_config["r_cm"]),
        "invert": bool(servo_config[f"invert_{axis}"]),
        "offset_deg": float(servo_config[f"offset_{axis}_deg"]),
    }


def servo_angle_for_tilt(tilt_deg: float, servo_config: dict, axis: str) -> float:
    return tilt_to_servo(tilt_deg, **_servo_axis(servo_config, axis))


def tilt_from_servo_angle(servo_deg: float, servo_config: dict, axis: str) -> float:
    return servo_to_tilt(servo_deg, **_servo_axis(servo_config, axis))


# --------------------------------------------------------------- Fake ESP32 ---


class FakeESP32:
    """Implementación Python del comportamiento del firmware, sin hardware."""

    def __init__(self, config: dict):
        self.config = config
        self.servo_config = dict(config["simulation"]["servo"])
        self.offset_limit_deg = float(self.servo_config["offset_limit_deg"])
        self.tilt_limit_min_deg = float(self.servo_config["tilt_limit_min_deg"])
        self.tilt_limit_max_deg = float(self.servo_config["tilt_limit_max_deg"])
        self.control_hz = float(config["simulation"].get("control_hz", 100))
        self.telemetry_hz = float(config["simulation"].get("telemetry_hz", 25))
        self.control_dt = 1.0 / self.control_hz
        self.level_ramp_dps = float(
            config["simulation"].get("level_ramp_dps", 30.0)
        )
        self.ball_timeout_ms = int(
            config["simulation"].get("ball_lost_timeout_ms", 200)
        )
        self.link_timeout_ms = int(
            config["simulation"].get("link_timeout_ms", 1000)
        )
        self._telemetry_every = max(
            1, int(round(self.control_hz / self.telemetry_hz))
        )
        self._tick_count = 0
        self.clock_ms = 0

        pid_config = config["control"]["pid"]
        self.gains = {}
        for axis in ("x", "y"):
            self.gains[axis] = {
                "kp": float(pid_config["kp"]),
                "ki": float(pid_config["ki"]),
                "kd": float(pid_config["kd"]),
            }
        self.tilt_limit = clamp(
            float(self.servo_config["tilt_limit_deg"]),
            self.tilt_limit_min_deg,
            self.tilt_limit_max_deg,
        )
        self.pid = {}
        for axis in ("x", "y"):
            self.pid[axis] = PIDController(
                kp=self.gains[axis]["kp"],
                ki=self.gains[axis]["ki"],
                kd=self.gains[axis]["kd"],
                output_limit_deg=self.tilt_limit,
                slew_rate_dps=float(self.servo_config["slew_rate_dps"]),
                derivative_filter=float(pid_config.get("d_filter", 0.15)),
                integral_limit_deg=float(
                    pid_config.get("integral_limit_deg", 3.0)
                ),
            )

        self.mode = 0
        self.auto_phase = 2  # 2=buscando, 3=estabilizando, 4=perdida
        self.raw_servo_hold = False
        self.setpoint_x = float(config["control"].get("setpoint_x_cm", 0.0))
        self.setpoint_y = float(config["control"].get("setpoint_y_cm", 0.0))
        self.position_limit_cm = float(config["plate"]["size_cm"]) / 2.0
        self.offset_x = float(self.servo_config["offset_x_deg"])
        self.offset_y = float(self.servo_config["offset_y_deg"])

        self.have_pose = False
        self.last_pose_found = False
        self.ball_x = 0.0
        self.ball_y = 0.0
        self.last_error_x = 0.0
        self.last_error_y = 0.0
        self.last_pose_ms = 0
        self.last_valid_rx_ms = 0
        self.auto_entered_ms = 0

        self.tilt_x = 0.0
        self.tilt_y = 0.0
        self.manual_tilt_x = 0.0
        self.manual_tilt_y = 0.0
        self.servo_x = servo_angle_for_tilt(0.0, self._servo_cfg_with_offsets(), "x")
        self.servo_y = servo_angle_for_tilt(0.0, self._servo_cfg_with_offsets(), "y")
        self.plate_tilt_x = 0.0
        self.plate_tilt_y = 0.0

    # -- utilidades ---------------------------------------------------------
    def _servo_cfg_with_offsets(self) -> dict:
        cfg = dict(self.servo_config)
        cfg["offset_x_deg"] = self.offset_x
        cfg["offset_y_deg"] = self.offset_y
        return cfg

    def _elapsed(self, since_ms: int, interval_ms: int) -> bool:
        return self.clock_ms - since_ms >= interval_ms

    def _state_code(self) -> int:
        if self.mode == 0:
            return 0
        if self.mode == 1:
            return 1
        return self.auto_phase

    def _set_auto_phase(self, phase: int) -> None:
        if phase == self.auto_phase:
            return
        self.auto_phase = phase
        for controller in self.pid.values():
            controller.reset()

    def _initial_auto_phase(self) -> int:
        if not self.have_pose:
            return 2
        if not self.last_pose_found:
            return 4
        if self._elapsed(self.last_pose_ms, self.ball_timeout_ms):
            return 4
        return 3

    def _update_auto_phase(self) -> None:
        link_ok = not self._elapsed(self.last_valid_rx_ms, self.link_timeout_ms)
        fresh = (
            self.have_pose
            and self.last_pose_found
            and not self._elapsed(self.last_pose_ms, self.ball_timeout_ms)
        )
        if not link_ok:
            target = 4
        elif fresh:
            target = 3
        elif self.have_pose and not self.last_pose_found:
            target = 4
        elif self.have_pose and self._elapsed(self.last_pose_ms, self.ball_timeout_ms):
            target = 4
        elif not self.have_pose:
            target = (
                4
                if self._elapsed(self.auto_entered_ms, self.ball_timeout_ms)
                else 2
            )
        else:
            target = 4
        self._set_auto_phase(target)

    def _apply_servo_conversion(self) -> None:
        servo_cfg = self._servo_cfg_with_offsets()
        if not self.raw_servo_hold:
            self.servo_x = servo_angle_for_tilt(self.tilt_x, servo_cfg, "x")
            self.servo_y = servo_angle_for_tilt(self.tilt_y, servo_cfg, "y")
        self.servo_x = clamp(
            self.servo_x,
            float(self.servo_config["min_deg"]),
            float(self.servo_config["max_deg"]),
        )
        self.servo_y = clamp(
            self.servo_y,
            float(self.servo_config["min_deg"]),
            float(self.servo_config["max_deg"]),
        )
        self.plate_tilt_x = tilt_from_servo_angle(
            self.servo_x, servo_cfg, "x"
        )
        self.plate_tilt_y = tilt_from_servo_angle(
            self.servo_y, servo_cfg, "y"
        )

    def _clamp_tilt(self, value: float) -> float:
        return clamp(value, -self.tilt_limit, self.tilt_limit)

    def _ramp_to_level(self) -> None:
        delta = self.level_ramp_dps * self.control_dt
        self.tilt_x = self._clamp_tilt(
            max(-delta, min(delta, 0.0 - self.tilt_x)) + self.tilt_x
        )
        self.tilt_y = self._clamp_tilt(
            max(-delta, min(delta, 0.0 - self.tilt_y)) + self.tilt_y
        )

    def _mode_command(self, new_mode: int) -> None:
        entering_auto = new_mode == 2 and self.mode != 2
        self.mode = new_mode
        self.raw_servo_hold = False
        for controller in self.pid.values():
            controller.reset()
        if new_mode == 2:
            self.auto_entered_ms = self.clock_ms
            self.auto_phase = self._initial_auto_phase()
            _ = entering_auto  # El simulador no tiene buzzer.
        elif new_mode == 1:
            self.manual_tilt_x = self.tilt_x
            self.manual_tilt_y = self.tilt_y

    # -- protocolo ----------------------------------------------------------
    def receive(self, line: str) -> list[str]:
        """Procesa una línea PC -> ESP32 y devuelve las respuestas (sin T)."""
        parsed = parse_host_command(line)
        if parsed is None:
            return ["ERR,linea_invalida"]
        command, args = parsed
        self.last_valid_rx_ms = self.clock_ms
        replies: list[str] = []

        if command == "P":
            x, y, found = args
            self.ball_x = clamp(
                x, -self.position_limit_cm, self.position_limit_cm
            )
            self.ball_y = clamp(
                y, -self.position_limit_cm, self.position_limit_cm
            )
            self.last_pose_found = bool(found)
            self.have_pose = True
            self.last_pose_ms = self.clock_ms
            replies.append("OK,P")
        elif command == "M":
            self._mode_command(args[0])
            replies.append("OK,M")
        elif command == "A":
            if self.mode != 1:
                replies.append("ERR,modo_no_manual")
            else:
                self.manual_tilt_x = clamp(args[0], -self.tilt_limit, self.tilt_limit)
                self.manual_tilt_y = clamp(args[1], -self.tilt_limit, self.tilt_limit)
                self.raw_servo_hold = False
                replies.append("OK,A")
        elif command == "V":
            if self.mode == 2:
                replies.append("ERR,modo_auto")
            else:
                self.servo_x = clamp(
                    args[0],
                    float(self.servo_config["min_deg"]),
                    float(self.servo_config["max_deg"]),
                )
                self.servo_y = clamp(
                    args[1],
                    float(self.servo_config["min_deg"]),
                    float(self.servo_config["max_deg"]),
                )
                self.raw_servo_hold = True
                self._apply_servo_conversion()
                replies.append("OK,V")
        elif command == "G":
            axis, kp, ki, kd = args
            values = {
                "kp": clamp(kp, *GAIN_LIMITS["kp"]),
                "ki": clamp(ki, *GAIN_LIMITS["ki"]),
                "kd": clamp(kd, *GAIN_LIMITS["kd"]),
            }
            axes = ("x", "y") if axis == "B" else (axis.lower(),)
            for selected_axis in axes:
                self.gains[selected_axis] = dict(values)
                self.pid[selected_axis].set_gains(**values)
            replies.append("OK,G")
        elif command == "S":
            self.setpoint_x = clamp(
                args[0], -self.position_limit_cm, self.position_limit_cm
            )
            self.setpoint_y = clamp(
                args[1], -self.position_limit_cm, self.position_limit_cm
            )
            replies.append("OK,S")
        elif command == "C":
            self.offset_x = clamp(
                args[0], -self.offset_limit_deg, self.offset_limit_deg
            )
            self.offset_y = clamp(
                args[1], -self.offset_limit_deg, self.offset_limit_deg
            )
            replies.append("OK,C")
        elif command == "L":
            self.tilt_limit = clamp(
                args[0], self.tilt_limit_min_deg, self.tilt_limit_max_deg
            )
            for controller in self.pid.values():
                controller.set_output_limit(self.tilt_limit)
            replies.append("OK,L")
        elif command == "W":
            replies.append("OK,W")
        elif command == "H":
            replies.append(f"HELLO,{FW_VERSION_SIM}")
            replies.append("OK,H")
        else:
            replies.append("ERR,comando_desconocido")
        return replies

    # -- control ------------------------------------------------------------
    def control_tick(self) -> list[str]:
        """Avanza 1/control_hz y devuelve las líneas T que correspondan."""
        self.clock_ms += int(round(1000.0 / self.control_hz))

        if self.mode == 2:
            self._update_auto_phase()
            fresh = (
                self.have_pose
                and self.last_pose_found
                and not self._elapsed(self.last_pose_ms, self.ball_timeout_ms)
                and not self._elapsed(
                    self.last_valid_rx_ms, self.link_timeout_ms
                )
            )
            if self.auto_phase == 3 and fresh:
                self.last_error_x = self.setpoint_x - self.ball_x
                self.last_error_y = self.setpoint_y - self.ball_y
                self.tilt_x = self.pid["x"].update(
                    self.setpoint_x, self.ball_x, self.control_dt
                )
                self.tilt_y = self.pid["y"].update(
                    self.setpoint_y, self.ball_y, self.control_dt
                )
            else:
                for controller in self.pid.values():
                    controller.reset()
                self.last_error_x = 0.0
                self.last_error_y = 0.0
                self._ramp_to_level()
        elif self.mode == 1:
            self.tilt_x = self._clamp_tilt(self.manual_tilt_x)
            self.tilt_y = self._clamp_tilt(self.manual_tilt_y)
            self.last_error_x = 0.0
            self.last_error_y = 0.0
        else:
            for controller in self.pid.values():
                controller.reset()
            self.last_error_x = 0.0
            self.last_error_y = 0.0
            self._ramp_to_level()

        self.tilt_x = self._clamp_tilt(self.tilt_x)
        self.tilt_y = self._clamp_tilt(self.tilt_y)
        self._apply_servo_conversion()

        self._tick_count += 1
        if self._tick_count % self._telemetry_every == 0:
            line = format_telemetry(
                ms=self.clock_ms,
                x=self.ball_x,
                y=self.ball_y,
                err_x=self.last_error_x,
                err_y=self.last_error_y,
                tilt_x=self.tilt_x,
                tilt_y=self.tilt_y,
                servo_x=self.servo_x,
                servo_y=self.servo_y,
                state=self._state_code(),
            )
            return [line]
        return []


# ----------------------------------------------------------- enlace simulado ---


class FakeSerialLink:
    """Interfaz equivalente a SerialLink, pero hablando con FakeESP32."""

    def __init__(self, fake: FakeESP32):
        self.fake = fake
        self.connected = False
        self.port_description = "SIMULADO"
        self.last_error = ""
        self.telemetry_count = 0
        self._latest = None
        self._last_lines: deque[str] = deque(maxlen=20)
        self._running = False

    def start(self) -> None:
        self._running = True
        self.connected = True

    def close(self) -> None:
        self._running = False
        self.connected = False

    def send(self, line: str) -> None:
        if not self._running:
            return
        for response in self.fake.receive(line):
            self._ingest_line(response)

    def feed_telemetry(self, lines: list[str]) -> None:
        for line in lines:
            self._ingest_line(line)

    def _ingest_line(self, line: str) -> None:
        if not line:
            return
        self._last_lines.append(line)
        telemetry = parse_telemetry(line)
        if telemetry is not None:
            self._latest = telemetry
            self.telemetry_count += 1
        elif line.startswith("ERR,"):
            self.last_error = line[4:]

    def latest_telemetry(self):
        return self._latest

    def pending_tx(self) -> int:
        return 0

    def send_pose(self, x: float, y: float, found: bool) -> None:
        from protocol import format_pose

        self.send(format_pose(x, y, found))


# ------------------------------------------------------------- simulación ----


class SyntheticCamera:
    """Genera los cuadros de la cámara ficticia con placa y ArUco."""

    def __init__(self, config: dict):
        self.config = config
        self.width = int(config["camera"]["width"])
        self.height = int(config["camera"]["height"])
        self.radius = int(config["simulation"]["ball_radius_px"])
        self.half_size_cm = float(config["plate"]["size_cm"]) / 2.0

        normalized = np.asarray(
            config["simulation"]["view_corners_normalized"], dtype=np.float32
        )
        self.corners = np.column_stack(
            (normalized[:, 0] * self.width, normalized[:, 1] * self.height)
        ).astype(np.float32)
        plate_cm = np.array(
            [
                [-self.half_size_cm, self.half_size_cm],
                [self.half_size_cm, self.half_size_cm],
                [self.half_size_cm, -self.half_size_cm],
                [-self.half_size_cm, -self.half_size_cm],
            ],
            dtype=np.float32,
        )
        self.plate_to_image = cv2.getPerspectiveTransform(plate_cm, self.corners)
        self.background = (180, 80, 0)  # BGR azul
        self.plate_color = (38, 38, 38)  # placa oscura mate
        self.ball_color = (0, 140, 255)  # naranja

    def plate_to_pixel(self, x_cm: float, y_cm: float) -> tuple[float, float]:
        point = np.array([[[float(x_cm), float(y_cm)]]], dtype=np.float32)
        result = cv2.perspectiveTransform(point, self.plate_to_image)[0, 0]
        return float(result[0]), float(result[1])

    def render(self, x_cm: float, y_cm: float) -> np.ndarray:
        frame = np.empty((self.height, self.width, 3), dtype=np.uint8)
        frame[:] = self.background

        plate = self.corners.astype(np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(frame, [plate], self.plate_color)
        cv2.polylines(frame, [plate], True, (210, 210, 210), 1, cv2.LINE_AA)
        draw_markers(frame, self.plate_to_image, self.config)

        px, py = self.plate_to_pixel(x_cm, y_cm)
        cv2.circle(
            frame,
            (int(round(px)), int(round(py))),
            self.radius,
            self.ball_color,
            thickness=-1,
            lineType=cv2.LINE_AA,
        )
        return frame


class Simulation:
    """Cámara sintética + FakeESP32 + física simple de la pelota."""

    def __init__(self, config: dict):
        self.config = config
        self.fake = FakeESP32(config)
        self.link = FakeSerialLink(self.fake)
        self.camera = SyntheticCamera(config)
        sim_config = config["simulation"]
        self.ball_x = float(sim_config.get("ball_start_x_cm", 6.0))
        self.ball_y = float(sim_config.get("ball_start_y_cm", 0.0))
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.gravity = float(sim_config.get("gravity_cm_s2", 981.0))
        self.half_size_cm = float(sim_config.get("plate_half_size_cm", 12.0))
        self.control_hz = float(sim_config.get("control_hz", 100))
        self.control_dt = 1.0 / self.control_hz
        self._accumulator = 0.0
        self.elapsed_s = 0.0
        self.started_at = time.perf_counter()

    def start(self) -> None:
        self.started_at = time.perf_counter()
        self.fake.clock_ms = 0
        self.link.start()

    def advance(self, dt_s: float) -> None:
        """Avanza control y física con paso fijo de 1/control_hz."""
        if dt_s <= 0.0:
            return
        dt_s = min(float(dt_s), 0.10)
        self._accumulator += dt_s
        self.elapsed_s += dt_s

        while self._accumulator >= self.control_dt:
            lines = self.fake.control_tick()
            if lines:
                self.link.feed_telemetry(lines)
            self._integrate_ball(self.control_dt)
            self._accumulator -= self.control_dt

    def _integrate_ball(self, dt: float) -> None:
        # a_cm = (5/7) * g * sin(tilt), con g en cm/s².
        accel_x = (
            (5.0 / 7.0)
            * self.gravity
            * math.sin(math.radians(self.fake.plate_tilt_x))
        )
        accel_y = (
            (5.0 / 7.0)
            * self.gravity
            * math.sin(math.radians(self.fake.plate_tilt_y))
        )

        self.velocity_x += accel_x * dt
        self.velocity_y += accel_y * dt
        self.ball_x += self.velocity_x * dt
        self.ball_y += self.velocity_y * dt

        # La pelota no rebota: al llegar al borde se limita y se detiene.
        if self.ball_x < -self.half_size_cm or self.ball_x > self.half_size_cm:
            self.ball_x = clamp(
                self.ball_x, -self.half_size_cm, self.half_size_cm
            )
            self.velocity_x = 0.0
        if self.ball_y < -self.half_size_cm or self.ball_y > self.half_size_cm:
            self.ball_y = clamp(
                self.ball_y, -self.half_size_cm, self.half_size_cm
            )
            self.velocity_y = 0.0

    def render_frame(self) -> np.ndarray:
        return self.camera.render(self.ball_x, self.ball_y)
