"""
Programa principal de la PC.

Uso típico:
    python main.py            # cámara real + ESP32
    python main.py --sim      # simulación completa, sin hardware

La PC detecta la pelota y envía su posición normalizada. El PID vive en el
ESP32 (o en el FakeESP32 cuando se usa --sim).
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from collections import deque
from pathlib import Path

import cv2
from camera import CameraThread
from config import DEFAULT_CONFIG_PATH, load_config
from gui import BallPlateGUI
from logger import TelemetryLogger
from protocol import format_mode
from serial_link import SerialLink
from sim import Simulation
from vision import (
    build_roi_mask,
    corners_to_pixels,
    detect_ball,
    normalize_point,
)

# TODO-HW: cámara real, ESP32, servos y calibraciones físicas.


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plataforma estabilizadora de pelota (ball and plate)"
    )
    parser.add_argument(
        "--sim",
        action="store_true",
        help="usar cámara sintética y FakeESP32 (no requiere hardware)",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="ruta de config.json (por defecto pc/config.json)",
    )
    parser.add_argument(
        "--camera",
        default=None,
        help="índice de cámara o URL, por ejemplo 0 o http://IP:8080/video",
    )
    parser.add_argument(
        "--port",
        default=None,
        help="puerto serie, por ejemplo COM5 (si se omite se autodetecta)",
    )
    return parser.parse_args(argv)


def _measured_fps(timestamps: deque) -> float:
    if len(timestamps) < 2:
        return 0.0
    elapsed = timestamps[-1] - timestamps[0]
    return (len(timestamps) - 1) / elapsed if elapsed > 0 else 0.0


def _resolve_log_directory(config: dict, config_path: Path) -> Path:
    configured = Path(config.get("logging", {}).get("directory", "logs"))
    if configured.is_absolute():
        return configured
    return config_path.parent / configured


class FrameProcessor:
    """Detección + normalización + envío de P, compartido por ambos modos."""

    def __init__(self, config: dict, link):
        self.config = config
        self.link = link
        self.roi_config = config["roi"]
        self.control_config = config["control"]
        self.last_error = ""

    def process(self, frame):
        height, width = frame.shape[:2]
        corners = corners_to_pixels(
            self.roi_config["corners_normalized"], width, height
        )
        mask = build_roi_mask((height, width, 3), corners)
        detection = detect_ball(frame, self.config["vision"], roi_mask=mask)

        ball_norm = None
        if detection.found:
            try:
                ball_norm = normalize_point(
                    detection.cx,
                    detection.cy,
                    corners,
                    perspective=bool(self.roi_config.get("perspective", False)),
                    invert_x=bool(self.control_config.get("invert_x", False)),
                    invert_y=bool(self.control_config.get("invert_y", False)),
                )
            except ValueError as exc:
                self.last_error = str(exc)
                ball_norm = None

        if ball_norm is None:
            self.link.send_pose(0.0, 0.0, False)
        else:
            self.link.send_pose(ball_norm[0], ball_norm[1], True)
        return detection, ball_norm


def run(config: dict, config_path: Path, args) -> int:
    camera = None
    link = None
    gui = None
    logger = None
    sim = None
    exit_code = 0

    initial_mode = int(config["control"].get("start_mode", 0))
    if initial_mode not in (0, 1, 2):
        initial_mode = 0
    if args.sim and bool(config["simulation"].get("auto_start", True)):
        initial_mode = 2

    try:
        # La ROI debe ser válida antes de abrir el lazo.
        corners_to_pixels(
            config["roi"]["corners_normalized"],
            int(config["camera"]["width"]),
            int(config["camera"]["height"]),
        )

        if args.sim:
            sim = Simulation(config)
            sim.start()
            link = sim.link
            print(
                "[sim] Cámara sintética y FakeESP32 activos. "
                "Esto valida la lógica, no el ajuste real de ganancias."
            )
        else:
            link = SerialLink(config, port_override=args.port)
            link.start()
            camera = CameraThread(config, source_override=args.camera)
            camera.start()

        log_directory = _resolve_log_directory(config, config_path)
        try:
            logger = TelemetryLogger(
                log_directory,
                enabled=bool(config.get("logging", {}).get("enabled", True)),
            )
        except OSError as exc:
            print(f"[log] No se pudo crear el CSV: {exc}")
            logger = TelemetryLogger(log_directory, enabled=False)

        # El enlace se inicia antes de la GUI para que los comandos iniciales
        # queden guardados o encolados, nunca perdidos.
        gui = BallPlateGUI(
            config=config,
            link=link,
            config_path=config_path,
            initial_mode=initial_mode,
        )

        processor = FrameProcessor(config, link)
        process_times: deque[float] = deque(maxlen=60)
        frame_times: deque[float] = deque(maxlen=60)
        last_telemetry_count = -1
        last_frame_index = -1
        last_detection = None
        last_norm = None
        last_frame = None
        last_render = 0.0

        if logger is not None and logger.path:
            print(f"[log] CSV: {logger.path}")
        print("[main] Ventana abierta. Q para salir, ESPACIO para paro de emergencia.")
        if not args.sim:
            if initial_mode == 0:
                print("[main] El firmware arranca apagado; presiona 2 para automático.")
            print(
                "[main] Esperando cámara y ESP32. El enlace y la cámara "
                "reintentan conectarse solos."
            )

        def log_telemetry() -> None:
            nonlocal last_telemetry_count
            if logger is None:
                return
            current_count = link.telemetry_count
            if current_count == last_telemetry_count:
                return
            last_telemetry_count = current_count
            telemetry = link.latest_telemetry()
            if telemetry is not None:
                logger.log(telemetry)

        def draw_current(frame, detection, ball_norm, camera_fps, process_ms, latency_ms):
            nonlocal last_render
            gui.render(
                frame,
                detection,
                ball_norm,
                camera_fps=camera_fps,
                vision_fps=_measured_fps(frame_times),
                processing_ms=process_ms,
                latency_ms=latency_ms,
            )
            last_render = time.perf_counter()

        def process_frame(frame, packet_timestamp=None):
            nonlocal last_detection, last_norm, last_frame
            started = time.perf_counter()
            detection, ball_norm = processor.process(frame)
            finished = time.perf_counter()
            process_ms = (finished - started) * 1000.0
            process_times.append(process_ms)
            frame_times.append(finished)
            latency_ms = (
                (finished - packet_timestamp) * 1000.0
                if packet_timestamp is not None
                else process_ms
            )
            last_detection = detection
            last_norm = ball_norm
            last_frame = frame
            return process_ms, latency_ms

        if args.sim:
            target_period = 1.0 / max(1.0, float(config["simulation"].get("fps", 60.0)))
            last_time = time.perf_counter()
            # Mostrar ya la ventana, incluso antes del primer cuadro.
            gui.render(None, None, None, 0.0, 0.0, 0.0, 0.0)
            while gui.running:
                loop_started = time.perf_counter()
                gui.process_events()
                if not gui.running:
                    break

                now = time.perf_counter()
                dt = min(0.1, max(0.0, now - last_time))
                last_time = now
                sim.advance(dt)

                frame_started = time.perf_counter()
                frame = sim.render_frame()
                process_ms, latency_ms = process_frame(frame, frame_started)
                log_telemetry()

                sim_fps = _measured_fps(frame_times)
                draw_current(
                    frame,
                    last_detection,
                    last_norm,
                    camera_fps=sim_fps,
                    process_ms=process_ms,
                    latency_ms=latency_ms,
                )

                elapsed = time.perf_counter() - loop_started
                if elapsed < target_period:
                    time.sleep(target_period - elapsed)
        else:
            # Mostrar la ventana en blanco hasta que llegue el primer cuadro.
            gui.render(None, None, None, 0.0, 0.0, 0.0, 0.0)
            while gui.running:
                gui.process_events()
                if not gui.running:
                    break

                packet = camera.get_latest()
                now = time.perf_counter()
                if packet is not None and packet.index != last_frame_index:
                    last_frame_index = packet.index
                    process_ms, latency_ms = process_frame(packet.frame, packet.timestamp)
                    log_telemetry()
                    draw_current(
                        packet.frame,
                        last_detection,
                        last_norm,
                        camera_fps=camera.fps,
                        process_ms=process_ms,
                        latency_ms=latency_ms,
                    )
                else:
                    log_telemetry()
                    # Refrescar mensajes/telemetría aunque la cámara tarde.
                    if now - last_render > 0.2:
                        if last_frame is not None:
                            draw_current(
                                last_frame,
                                last_detection,
                                last_norm,
                                camera_fps=camera.fps,
                                process_ms=process_times[-1] if process_times else 0.0,
                                latency_ms=0.0,
                            )
                        else:
                            draw_current(
                                None,
                                None,
                                None,
                                camera_fps=0.0,
                                process_ms=0.0,
                                latency_ms=0.0,
                            )
                time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[main] Interrumpido por el usuario.")
    except Exception as exc:
        exit_code = 1
        print(f"\n[main] Error fatal: {exc}")
        traceback.print_exc()
    finally:
        # Seguridad: si el programa se cierra, pedir modo apagado antes de cerrar.
        try:
            if link is not None:
                link.send(format_mode(0))
        except Exception:
            pass
        try:
            if link is not None and link.connected:
                time.sleep(0.15)
        except Exception:
            pass

        if camera is not None:
            camera.stop()
        if logger is not None:
            logger.close()
            if logger.path:
                print(f"[log] Guardado: {logger.path}")
        if link is not None:
            try:
                link.close()
            except Exception:
                pass
        if gui is not None:
            gui.close()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass

    return exit_code


def main(argv=None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config).expanduser().resolve()
    try:
        config = load_config(config_path)
    except (OSError, ValueError) as exc:
        print(f"[main] No se pudo leer {config_path}: {exc}")
        return 2
    return run(config, config_path, args)


if __name__ == "__main__":
    sys.exit(main())
