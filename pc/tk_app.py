"""
Interfaz alternativa en Tkinter con cámara, simulación 2D y gráficas.

Se usa con:
    python main.py --tk
    python main.py --tk --sim

La interfaz OpenCV sigue disponible sin --tk.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import traceback
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from PIL import Image, ImageTk
from tkinter import messagebox, ttk

from camera import CameraThread
from config import DEFAULT_CONFIG_PATH, ensure_default_config, load_config, save_config
from devices import setup_devices
from logger import TelemetryLogger
from markers import MarkerTracker
from protocol import (
    format_gains,
    format_mode,
    format_setpoint,
)
from serial_link import SerialLink
from sim import Simulation
from vision import BallDetection, detect_ball

ROOT = Path(__file__).resolve().parents[1]
STATE_NAMES = {
    0: "APAGADO",
    1: "MANUAL",
    2: "BUSCANDO",
    3: "ESTABILIZANDO",
    4: "PELOTA PERDIDA",
}


def _resolve_log_directory(config: dict, config_path: Path) -> Path:
    configured = Path(config.get("logging", {}).get("directory", "logs"))
    if configured.is_absolute():
        return configured
    return config_path.parent / configured


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Interfaz Tkinter de Plataforma Pelota")
    parser.add_argument("--sim", action="store_true")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--camera", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--setup-devices", action="store_true")
    return parser.parse_args(argv)


class TkApp:
    def __init__(self, root, config, config_path, link, camera, sim, logger, simulation_mode):
        self.root = root
        self.config = config
        self.config_path = Path(config_path)
        self.link = link
        self.camera = camera
        self.sim = sim
        self.logger = logger
        self.simulation_mode = simulation_mode
        self.tracker = MarkerTracker(config)

        self.position_limit_cm = float(config["plate"]["size_cm"]) / 2.0
        self.mode = int(config["control"].get("start_mode", 0))
        if simulation_mode and bool(config["simulation"].get("auto_start", True)):
            self.mode = 2
        if self.mode not in (0, 1, 2):
            self.mode = 0
        pid = config["control"]["pid"]
        self.gains = {
            "kp": float(pid["kp"]),
            "ki": float(pid["ki"]),
            "kd": float(pid["kd"]),
        }
        self.invert_x = bool(config["control"].get("invert_x", False))
        self.invert_y = bool(config["control"].get("invert_y", False))
        self.setpoint_x = float(config["control"].get("setpoint_x_cm", 0.0))
        self.setpoint_y = float(config["control"].get("setpoint_y_cm", 0.0))
        self._gains_job = None
        self._closing = False

        self.last_pose = None
        self.last_detection = BallDetection(0.0, 0.0, 0.0, False)
        self.last_ball_cm = None
        self.last_frame = None
        self.last_frame_size = (640, 480)
        self.last_frame_index = -1
        self.last_process_ms = 0.0
        self.last_latency_ms = 0.0
        self.last_telemetry_count = -1
        self.last_telemetry = None
        self.last_history = 0.0
        self.history = deque(maxlen=600)
        self.frame_times = deque(maxlen=60)
        self._last_tick = time.perf_counter()
        self._photo = None
        self._camera_frame_bgr = None
        self._camera_rect = None
        self._camera_item = None

        self.mode_var = tk.StringVar(value="")
        self.state_var = tk.StringVar(value="SIN TELEMETRIA")
        self.link_var = tk.StringVar(value="")
        self.plate_var = tk.StringVar(value="ArUco 0/4")
        self.ball_var = tk.StringVar(value="sin pelota")
        self.fps_var = tk.StringVar(value="0 fps")
        self.sp_var = tk.StringVar(value="")
        self.message_var = tk.StringVar(value="Listo")
        self.kp_label = tk.StringVar(value="")
        self.ki_label = tk.StringVar(value="")
        self.kd_label = tk.StringVar(value="")
        self._update_pid_labels()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<space>", lambda _event: self.emergency())
        self.root.bind("1", lambda _event: self.set_mode(1))
        self.root.bind("2", lambda _event: self.set_mode(2))
        self.root.bind("0", lambda _event: self.set_mode(0))
        self.root.bind("q", lambda _event: self.close())
        self.root.bind("<F11>", lambda _event: self._toggle_fullscreen())
        self.root.bind("<Escape>", lambda _event: self._exit_fullscreen())

        self.link.send(
            format_gains("B", self.gains["kp"], self.gains["ki"], self.gains["kd"])
        )
        self._send_setpoint()
        self.link.send(format_mode(self.mode))
        self._update_mode_labels()
        self.root.after(20, self._tick)

    # ------------------------------------------------------------------ UI ---
    def _build_ui(self):
        bg = "#f5f5f7"
        card = "#ffffff"
        text = "#1d1d1f"
        muted = "#6e6e73"
        blue = "#0071e3"
        border = "#d2d2d7"
        self.root.title("CENTRA - Plataforma Pelota")
        self.root.configure(bg=bg)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        width = max(900, min(1440, sw - 80))
        height = max(580, min(900, sh - 100))
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 3)
        self._window_geometry = f"{width}x{height}+{x}+{y}"
        self.root.geometry(self._window_geometry)
        self.root.minsize(900, 560)
        self._fullscreen = False

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 9))
        style.configure("Hint.TLabel", background=bg, foreground=muted, font=("Segoe UI", 8))
        style.configure("Value.TLabel", background=bg, foreground=text, font=("Consolas", 9))
        style.configure(
            "TLabelframe", background=bg, bordercolor=border,
            borderwidth=1, relief="solid"
        )
        style.configure(
            "TLabelframe.Label", background=bg, foreground=text,
            font=("Segoe UI", 9, "bold")
        )
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure(
            "TNotebook.Tab", background=bg, foreground=muted,
            padding=(14, 8), font=("Segoe UI", 9)
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", card)],
            foreground=[("selected", text)],
        )
        style.configure(
            "TButton", background=card, foreground=text,
            padding=(8, 5), font=("Segoe UI", 9), borderwidth=1
        )
        style.map("TButton", background=[("active", "#ececf0")])
        style.configure(
            "Accent.TButton", background=blue, foreground="white",
            padding=(8, 6), font=("Segoe UI", 9, "bold")
        )
        style.map("Accent.TButton", background=[("active", "#0062c4")])
        style.configure(
            "Gold.TButton", background=blue, foreground="white",
            padding=(8, 6), font=("Segoe UI", 9, "bold")
        )
        style.map("Gold.TButton", background=[("active", "#0062c4")])
        style.configure(
            "Danger.TButton", background="#d70015", foreground="white",
            padding=(8, 6), font=("Segoe UI", 9, "bold")
        )
        style.map("Danger.TButton", background=[("active", "#b00012")])
        style.configure("TPanedwindow", background=bg)
        style.configure(
            "TCheckbutton", background=bg, foreground=text,
            font=("Segoe UI", 9)
        )
        style.map("TCheckbutton", background=[("active", bg)])
        style.configure("TScale", background=bg, troughcolor="#e5e5ea")

        header = tk.Frame(self.root, bg=card, height=84)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        brand = tk.Frame(header, bg=card)
        brand.pack(side=tk.LEFT, padx=18, pady=10)
        tk.Label(
            brand, text="CENTRA", bg=card, fg=text,
            font=("Segoe UI", 26, "bold")
        ).pack(anchor=tk.W)
        tk.Label(
            brand, text="ÁGUILAS IMPERIALES  ·  Ball & Plate",
            bg=card, fg=muted, font=("Segoe UI", 9)
        ).pack(anchor=tk.W)
        header_right = tk.Frame(header, bg=card)
        header_right.pack(side=tk.RIGHT, padx=14)
        buttons = tk.Frame(header_right, bg=card)
        buttons.pack(anchor=tk.E)
        tk.Button(
            buttons, text="Pantalla completa", command=self._toggle_fullscreen,
            bg=card, fg=blue, activebackground="#e8f1fc", activeforeground=blue,
            relief=tk.FLAT, borderwidth=0, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            buttons, text="Pantalla 2", command=self._move_to_second_screen,
            bg=card, fg=blue, activebackground="#e8f1fc", activeforeground=blue,
            relief=tk.FLAT, borderwidth=0, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=3)
        tk.Label(
            header_right, textvariable=self.link_var, bg=card, fg=muted,
            font=("Consolas", 9)
        ).pack(anchor=tk.E, pady=(3, 0))
        tk.Frame(self.root, bg=border, height=1).pack(fill=tk.X)

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        left = ttk.Notebook(body)
        self.main_tabs = left
        right_host = ttk.Frame(body)
        right_canvas = tk.Canvas(
            right_host, bg=bg, highlightthickness=0, width=360
        )
        right_scroll = ttk.Scrollbar(
            right_host, orient=tk.VERTICAL, command=right_canvas.yview
        )
        right = ttk.Frame(right_canvas)
        right_window = right_canvas.create_window(
            (0, 0), window=right, anchor=tk.NW
        )
        right.bind(
            "<Configure>",
            lambda _event: right_canvas.configure(
                scrollregion=right_canvas.bbox("all")
            ),
        )
        right_canvas.bind(
            "<Configure>",
            lambda event: right_canvas.itemconfigure(right_window, width=event.width),
        )
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _wheel(event):
            right_canvas.yview_scroll(int(-event.delta / 120), "units")

        right_canvas.bind(
            "<Enter>", lambda _event: right_canvas.bind_all("<MouseWheel>", _wheel)
        )
        right_canvas.bind(
            "<Leave>", lambda _event: right_canvas.unbind_all("<MouseWheel>")
        )
        self._right_canvas = right_canvas
        body.add(left, weight=4)
        body.add(right_host, weight=1)

        # Vista split: cámara + simulación/estado, siempre juntas.
        tab_split = ttk.Frame(left)
        left.add(tab_split, text="Vista split")
        split = ttk.Panedwindow(tab_split, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True)
        camera_panel = ttk.LabelFrame(split, text="CÁMARA / ARUCO", padding=6)
        plate_panel = ttk.LabelFrame(split, text="PLATAFORMA 2D", padding=6)
        split.add(camera_panel, weight=3)
        split.add(plate_panel, weight=2)
        self.camera_canvas = tk.Canvas(
            camera_panel, width=320, height=240, bg="#0b0b0d", highlightthickness=0
        )
        self.camera_canvas.pack(fill=tk.BOTH, expand=True)
        self.camera_canvas.bind("<Button-1>", self._on_camera_click)
        self.camera_canvas.bind("<Configure>", lambda _event: self._redraw_camera())
        ttk.Label(
            camera_panel,
            text="Clic dentro de la placa para fijar el setpoint",
            style="Hint.TLabel",
        ).pack(anchor=tk.W, pady=(4, 2))
        self.plate_canvas = tk.Canvas(
            plate_panel, width=240, height=200, bg="#0b0b0d", highlightthickness=0
        )
        self.plate_canvas.pack(fill=tk.BOTH, expand=True)
        self.plate_canvas.bind("<Button-1>", self._on_plate_click)
        ttk.Label(
            plate_panel,
            text="Pelota, setpoint e inclinación comandada",
            style="Hint.TLabel",
        ).pack(anchor=tk.W, pady=(4, 2))

        # Pestaña gráficas
        tab_graph = ttk.Frame(left)
        left.add(tab_graph, text="Gráficas")
        self.figure = Figure(figsize=(6.5, 4.8), dpi=90)
        self.figure.patch.set_facecolor("#ffffff")
        self.ax_err = self.figure.add_subplot(311)
        self.ax_tilt = self.figure.add_subplot(312, sharex=self.ax_err)
        self.ax_servo = self.figure.add_subplot(313, sharex=self.ax_err)
        self.ax_err.set_ylabel("error (cm)")
        self.ax_tilt.set_ylabel("tilt (deg)")
        self.ax_servo.set_ylabel("servo (deg)")
        self.ax_servo.set_xlabel("segundos (ventana de 10 s)")
        for axis in (self.ax_err, self.ax_tilt, self.ax_servo):
            axis.set_facecolor("#fbfdff")
            axis.grid(True, color="#dbe4ef", alpha=0.8)
            axis.tick_params(labelsize=7, colors="#475569")
            for spine in axis.spines.values():
                spine.set_color("#cbd5e1")
        (self.line_ex,) = self.ax_err.plot([], [], label="err X", color="#e74c3c")
        (self.line_ey,) = self.ax_err.plot([], [], label="err Y", color="#3498db")
        (self.line_tx,) = self.ax_tilt.plot([], [], label="tilt X", color="#e67e22")
        (self.line_ty,) = self.ax_tilt.plot([], [], label="tilt Y", color="#16a085")
        (self.line_sx,) = self.ax_servo.plot([], [], label="servo X", color="#8e44ad")
        (self.line_sy,) = self.ax_servo.plot([], [], label="servo Y", color="#2c3e50")
        self.ax_err.legend(loc="upper right", fontsize=7, ncol=2)
        self.ax_tilt.legend(loc="upper right", fontsize=7, ncol=2)
        self.ax_servo.legend(loc="upper right", fontsize=7, ncol=2)
        self.figure.tight_layout()
        self.graph_canvas = FigureCanvasTkAgg(self.figure, master=tab_graph)
        self.graph_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Pestaña servos por separado (la anterior los muestra juntos).
        tab_servo = ttk.Frame(left)
        left.add(tab_servo, text="Servos X/Y separados")
        self.servo_figure = Figure(figsize=(6.5, 4.8), dpi=90)
        self.servo_figure.patch.set_facecolor("#ffffff")
        self.ax_sx = self.servo_figure.add_subplot(211)
        self.ax_sy = self.servo_figure.add_subplot(212, sharex=self.ax_sx)
        for axis, title in ((self.ax_sx, "servo X (deg)"), (self.ax_sy, "servo Y (deg)")):
            axis.set_ylabel(title)
            axis.set_facecolor("#fbfdff")
            axis.grid(True, color="#dbe4ef", alpha=0.8)
            axis.tick_params(labelsize=7, colors="#475569")
            for spine in axis.spines.values():
                spine.set_color("#cbd5e1")
        self.ax_sy.set_xlabel("segundos (ventana de 10 s)")
        (self.line_sx_sep,) = self.ax_sx.plot([], [], label="servo X", color="#8e44ad")
        (self.line_sy_sep,) = self.ax_sy.plot([], [], label="servo Y", color="#2c3e50")
        self.ax_sx.legend(loc="upper right", fontsize=7)
        self.ax_sy.legend(loc="upper right", fontsize=7)
        self.servo_figure.tight_layout()
        self.servo_canvas = FigureCanvasTkAgg(self.servo_figure, master=tab_servo)
        self.servo_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Pestaña datos
        tab_data = ttk.Frame(left)
        left.add(tab_data, text="Datos")
        self.log_text = tk.Text(
            tab_data, height=18, state=tk.DISABLED, font=("Consolas", 9),
            bg="#0b1220", fg="#cfe3ff", insertbackground="#cfe3ff",
            relief=tk.FLAT, padx=8, pady=6
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        row = ttk.Frame(tab_data)
        row.pack(fill=tk.X)

        def open_logs():
            directory = _resolve_log_directory(self.config, self.config_path)
            directory.mkdir(parents=True, exist_ok=True)
            try:
                import os
                os.startfile(str(directory))
            except Exception as exc:
                messagebox.showwarning("Datos", f"No se pudo abrir la carpeta: {exc}")

        ttk.Button(row, text="Abrir carpeta de logs", command=open_logs).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(row, text="Limpiar", command=self._clear_log).pack(side=tk.LEFT, padx=4, pady=4)

        # Panel derecho
        tk.Label(
            right, text="PANEL DE CONTROL", bg="#f5f5f7", fg="#1d1d1f",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor=tk.W, padx=8, pady=(2, 2))

        status = ttk.LabelFrame(right, text="Estado", padding=8)
        status.pack(fill=tk.X, padx=4, pady=4)
        for label, variable in (
            ("Modo", self.mode_var),
            ("Estado", self.state_var),
            ("Placa", self.plate_var),
            ("Pelota", self.ball_var),
            ("Setpoint", self.sp_var),
            ("Rendimiento", self.fps_var),
        ):
            row = ttk.Frame(status)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label + ":", width=10).pack(side=tk.LEFT)
            ttk.Label(
                row, textvariable=variable, style="Value.TLabel", wraplength=210
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        controls = ttk.LabelFrame(right, text="CONTROL", padding=8)
        controls.pack(fill=tk.X, padx=4, pady=4)
        for label_text, mode in (
            ("0 · Apagado", 0),
            ("1 · Manual", 1),
            ("2 · Automático", 2),
        ):
            ttk.Button(
                controls, text=label_text, style="Accent.TButton",
                command=lambda m=mode: self.set_mode(m)
            ).pack(fill=tk.X, pady=2)
        ttk.Button(
            controls, text="■ PARO DE EMERGENCIA", style="Danger.TButton",
            command=self.emergency
        ).pack(fill=tk.X, pady=(6, 2))
        ttk.Button(
            controls, text="Centrar setpoint", command=lambda: self._set_setpoint(0.0, 0.0)
        ).pack(fill=tk.X, pady=1)
        sp_row = ttk.Frame(controls)
        sp_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(sp_row, text="SP cm", width=6).pack(side=tk.LEFT)
        self.sp_x_var = tk.StringVar(value=f"{self.setpoint_x:.2f}")
        self.sp_y_var = tk.StringVar(value=f"{self.setpoint_y:.2f}")
        ttk.Entry(sp_row, textvariable=self.sp_x_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Entry(sp_row, textvariable=self.sp_y_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            sp_row, text="Aplicar", command=self._apply_setpoint_entries
        ).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        pid = ttk.LabelFrame(right, text="GANANCIAS PID · en vivo", padding=8)
        pid.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(
            pid,
            text="Kp = corrección ahora · Ki = error acumulado · Kd = freno.\n"
                 "NO son drivers, cámaras ni puertos: son números del controlador.",
            style="Hint.TLabel", wraplength=300
        ).pack(anchor=tk.W, pady=(0, 4))
        self.kp_var = tk.DoubleVar(value=self.gains["kp"])
        self.ki_var = tk.DoubleVar(value=self.gains["ki"])
        self.kd_var = tk.DoubleVar(value=self.gains["kd"])
        for title, variable, maximum, label_var in (
            ("Kp", self.kp_var, 5.0, self.kp_label),
            ("Ki", self.ki_var, 1.0, self.ki_label),
            ("Kd", self.kd_var, 5.0, self.kd_label),
        ):
            row = ttk.Frame(pid)
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=title, width=3).pack(side=tk.LEFT)
            ttk.Scale(
                row, from_=0.0, to=maximum, variable=variable,
                orient=tk.HORIZONTAL, command=self._on_gain_change
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(row, textvariable=label_var, width=7, style="Value.TLabel").pack(side=tk.LEFT)

        actions = ttk.LabelFrame(right, text="SERVOS Y AJUSTES", padding=8)
        actions.pack(fill=tk.X, padx=4, pady=4)
        inv_row = ttk.Frame(actions)
        inv_row.pack(fill=tk.X, pady=(0, 2))
        self.invert_x_var = tk.BooleanVar(value=self.invert_x)
        self.invert_y_var = tk.BooleanVar(value=self.invert_y)
        ttk.Checkbutton(
            inv_row, text="Invertir X", variable=self.invert_x_var,
            command=self._on_invert_change
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(
            inv_row, text="Invertir Y", variable=self.invert_y_var,
            command=self._on_invert_change
        ).pack(side=tk.LEFT)
        ttk.Label(
            actions,
            text="Marcá el eje que tira al revés. Se aplica en vivo y no "
                 "necesita recompilar.",
            style="Hint.TLabel", wraplength=300
        ).pack(anchor=tk.W, pady=(0, 4))
        ttk.Button(
            actions, text="Guardar ajustes en el ESP32", style="Gold.TButton",
            command=self._save
        ).pack(fill=tk.X, pady=2)
        ttk.Label(
            actions, text="Guarda Kp/Ki/Kd y offsets en la memoria del ESP32 (NVS).",
            style="Hint.TLabel", wraplength=300
        ).pack(anchor=tk.W, pady=(0, 3))
        ttk.Button(
            actions, text="Cámara y puerto USB", style="Accent.TButton",
            command=self._configure_devices
        ).pack(fill=tk.X, pady=2)
        ttk.Label(
            actions, text="El driver USB y la app de cámara se instalan en Windows aparte.",
            style="Hint.TLabel", wraplength=300
        ).pack(anchor=tk.W, pady=(0, 3))
        ttk.Button(
            actions, text="Calibrar color (abre OpenCV)",
            command=self._calibrate_color
        ).pack(fill=tk.X, pady=1)
        ttk.Button(
            actions, text="¿Qué significa cada cosa?", command=self._show_help
        ).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Salir", command=self.close).pack(fill=tk.X, pady=(6, 1))

        footer = tk.Frame(self.root, bg=card, height=30)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        tk.Frame(footer, bg=border, height=1).pack(fill=tk.X, side=tk.TOP)
        tk.Label(
            footer, textvariable=self.message_var, bg=card, fg=text,
            font=("Segoe UI", 9), anchor=tk.W
        ).pack(side=tk.LEFT, padx=12, fill=tk.X, expand=True)
        tk.Label(
            footer, text="CENTRA · © 2026 ÁGUILAS IMPERIALES", bg=card, fg=muted,
            font=("Segoe UI", 8)
        ).pack(side=tk.RIGHT, padx=12)

    # ---------------------------------------------------------------- control ---
    def _update_pid_labels(self):
        self.kp_label.set(f"{self.gains['kp']:.2f}")
        self.ki_label.set(f"{self.gains['ki']:.2f}")
        self.kd_label.set(f"{self.gains['kd']:.2f}")

    def _on_gain_change(self, _value=None):
        try:
            self.gains = {
                "kp": round(float(self.kp_var.get()), 2),
                "ki": round(float(self.ki_var.get()), 2),
                "kd": round(float(self.kd_var.get()), 2),
            }
        except (tk.TclError, ValueError):
            return
        self._update_pid_labels()
        if self._gains_job is not None:
            try:
                self.root.after_cancel(self._gains_job)
            except tk.TclError:
                pass
        self._gains_job = self.root.after(120, self._send_gains)

    def _send_gains(self):
        self._gains_job = None
        self.link.send(format_gains("B", self.gains["kp"], self.gains["ki"], self.gains["kd"]))
        self._log(f"> G,B,{self.gains['kp']:.2f},{self.gains['ki']:.2f},{self.gains['kd']:.2f}")

    def _update_mode_labels(self):
        names = {0: "APAGADO", 1: "MANUAL", 2: "AUTOMÁTICO"}
        self.mode_var.set(names.get(self.mode, "?"))

    def set_mode(self, mode: int):
        self.mode = int(mode)
        self.link.send(format_mode(self.mode))
        self._update_mode_labels()
        self._log(f"> M,{self.mode}")
        self.message_var.set(f"Modo {self.mode_var.get()}")

    def emergency(self):
        self.set_mode(0)
        self.message_var.set("PARO DE EMERGENCIA: modo apagado")

    def _send_setpoint(self):
        self.setpoint_x = max(-self.position_limit_cm, min(self.position_limit_cm, self.setpoint_x))
        self.setpoint_y = max(-self.position_limit_cm, min(self.position_limit_cm, self.setpoint_y))
        sign_x = -1.0 if self.invert_x else 1.0
        sign_y = -1.0 if self.invert_y else 1.0
        self.link.send(
            format_setpoint(self.setpoint_x * sign_x, self.setpoint_y * sign_y)
        )
        self.sp_var.set(f"x={self.setpoint_x:+.2f} y={self.setpoint_y:+.2f} cm")
        if hasattr(self, "sp_x_var"):
            self.sp_x_var.set(f"{self.setpoint_x:.2f}")
            self.sp_y_var.set(f"{self.setpoint_y:.2f}")
        self._log(f"> S,{self.setpoint_x:.2f},{self.setpoint_y:.2f}")

    def _set_setpoint(self, x_cm: float, y_cm: float):
        self.setpoint_x = max(-self.position_limit_cm, min(self.position_limit_cm, float(x_cm)))
        self.setpoint_y = max(-self.position_limit_cm, min(self.position_limit_cm, float(y_cm)))
        self._send_setpoint()

    def _apply_setpoint_entries(self):
        try:
            x_cm = float(self.sp_x_var.get().replace(",", "."))
            y_cm = float(self.sp_y_var.get().replace(",", "."))
        except ValueError:
            self.message_var.set("Setpoint inválido: usá números en cm.")
            return
        self._set_setpoint(x_cm, y_cm)

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)
        if not self._fullscreen:
            self.root.geometry(self._window_geometry)

    def _exit_fullscreen(self):
        if self._fullscreen:
            self._fullscreen = False
            self.root.attributes("-fullscreen", False)
            self.root.geometry(self._window_geometry)

    def _move_to_second_screen(self):
        self._exit_fullscreen()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        width = max(900, min(1440, sw - 80))
        height = max(580, min(900, sh - 100))
        self.root.geometry(f"{width}x{height}+{sw}+0")
        self.message_var.set("Ventana movida a la pantalla de la derecha.")

    def _on_camera_click(self, event):
        pose = self.last_pose
        if pose is None or not pose.valid or self._camera_rect is None:
            self.message_var.set("No hay placa ArUco detectada.")
            return
        x0, y0, draw_w, draw_h = self._camera_rect
        if not (x0 <= event.x <= x0 + draw_w and y0 <= event.y <= y0 + draw_h):
            return
        frame_w, frame_h = self.last_frame_size
        fx = (event.x - x0) * frame_w / max(1, draw_w)
        fy = (event.y - y0) * frame_h / max(1, draw_h)
        if not pose.contains_pixel(fx, fy):
            self.message_var.set("El clic debe estar dentro de la placa.")
            return
        point = pose.pixel_to_cm(fx, fy)
        if point is not None:
            self._set_setpoint(*point)

    def _on_plate_click(self, event):
        width = max(120, self.plate_canvas.winfo_width())
        height = max(120, self.plate_canvas.winfo_height())
        size = min(width, height)
        if size < 80:
            return
        margin = size * 0.08
        scale = (size - 2 * margin) / (2 * self.position_limit_cm)
        center_x = (width - size) / 2.0 + size / 2.0
        center_y = (height - size) / 2.0 + size / 2.0
        x_cm = (event.x - center_x) / scale
        y_cm = (center_y - event.y) / scale
        self._set_setpoint(x_cm, y_cm)

    # ------------------------------------------------------------------- I/O ---
    def _process_frame(self, frame, packet_timestamp):
        started = time.perf_counter()
        pose = self.tracker.detect(frame)
        detection = BallDetection(0.0, 0.0, 0.0, False)
        ball_cm = None
        if pose.valid:
            mask = pose.plate_mask(frame.shape)
            detection = detect_ball(frame, self.config["vision"], plate_mask=mask)
            if detection.found:
                point = pose.pixel_to_cm(detection.cx, detection.cy)
                if point is not None:
                    x_cm, y_cm = point
                    if abs(x_cm) <= self.position_limit_cm and abs(y_cm) <= self.position_limit_cm:
                        ball_cm = (x_cm, y_cm)
        if ball_cm is None:
            self.link.send_pose(0.0, 0.0, False)
        else:
            sign_x = -1.0 if self.invert_x else 1.0
            sign_y = -1.0 if self.invert_y else 1.0
            self.link.send_pose(ball_cm[0] * sign_x, ball_cm[1] * sign_y, True)

        finished = time.perf_counter()
        self.last_process_ms = (finished - started) * 1000.0
        self.last_latency_ms = (finished - packet_timestamp) * 1000.0
        self.last_pose = pose
        self.last_detection = detection
        self.last_ball_cm = ball_cm
        self.last_frame = frame
        self.last_frame_size = (frame.shape[1], frame.shape[0])
        self.frame_times.append(finished)
        self._render_camera(frame, detection, ball_cm, pose)
        self._render_plate(ball_cm)

    def _tick(self):
        if self._closing:
            return
        try:
            now = time.perf_counter()
            if self.simulation_mode and self.sim is not None:
                dt = min(0.1, max(0.0, now - self._last_tick))
                self._last_tick = now
                self.sim.advance(dt)
                frame = self.sim.render_frame()
                self._process_frame(frame, time.perf_counter())
            else:
                packet = self.camera.get_latest() if self.camera is not None else None
                if packet is not None and packet.index != self.last_frame_index:
                    self.last_frame_index = packet.index
                    self._process_frame(packet.frame, packet.timestamp)
            self._update_live_status()
            self._update_graphs()
        except Exception as exc:
            self.message_var.set(f"Error: {exc}")
            traceback.print_exc()
        finally:
            if not self._closing:
                self.root.after(20, self._tick)

    def _update_live_status(self):
        telemetry = self.link.latest_telemetry() if self.link.connected else None
        if telemetry is not None and self.link.telemetry_count != self.last_telemetry_count:
            self.last_telemetry_count = self.link.telemetry_count
            self.last_telemetry = telemetry
            sign_x = -1.0 if self.invert_x else 1.0
            sign_y = -1.0 if self.invert_y else 1.0
            self.state_var.set(STATE_NAMES.get(telemetry.state, "?"))
            self.ball_var.set(
                f"x={telemetry.x * sign_x:+.2f} "
                f"y={telemetry.y * sign_y:+.2f} cm"
            )
            if self.last_history == 0.0:
                self.last_history = time.perf_counter()
            self.history.append(
                (
                    time.perf_counter(),
                    telemetry.err_x * sign_x,
                    telemetry.err_y * sign_y,
                    telemetry.tilt_x * sign_x,
                    telemetry.tilt_y * sign_y,
                    telemetry.servo_x,
                    telemetry.servo_y,
                )
            )
            self._log(
                f"< T {telemetry.ms} x={telemetry.x * sign_x:+.2f} "
                f"y={telemetry.y * sign_y:+.2f} "
                f"err=({telemetry.err_x * sign_x:+.2f},"
                f"{telemetry.err_y * sign_y:+.2f}) "
                f"tilt=({telemetry.tilt_x * sign_x:+.2f},"
                f"{telemetry.tilt_y * sign_y:+.2f})"
            )
        elif self.last_ball_cm is not None:
            self.ball_var.set(f"x={self.last_ball_cm[0]:+.2f} y={self.last_ball_cm[1]:+.2f} cm")

        self.link_var.set(
            f"LINK: {self.link.port_description if self.link.connected else 'SIN ENLACE'}"
        )
        if self.last_pose is not None and self.last_pose.valid:
            self.plate_var.set(
                f"ArUco {self.last_pose.marker_count()}/4"
                + (" (última pose)" if self.last_pose.stale else "")
            )
        else:
            self.plate_var.set("ArUco 0/4 - placa no detectada")
        if self.simulation_mode:
            fps = self._measured_fps()
            self.fps_var.set(f"SIM {fps:.1f} fps | {self.last_process_ms:.1f} ms")
        else:
            fps = self.camera.fps if self.camera is not None else 0.0
            self.fps_var.set(f"CAM {fps:.1f} fps | {self.last_latency_ms:.1f} ms")

    def _measured_fps(self):
        if len(self.frame_times) < 2:
            return 0.0
        elapsed = self.frame_times[-1] - self.frame_times[0]
        return (len(self.frame_times) - 1) / elapsed if elapsed > 0 else 0.0

    # --------------------------------------------------------------- dibujo ---
    def _draw_common_overlay(self, image, pose, detection, ball_cm):
        if pose is not None and pose.valid:
            corners = np.asarray(pose.plate_corners_px, dtype=np.int32)
            color = (0, 220, 255) if not pose.stale else (150, 150, 150)
            cv2.polylines(image, [corners.reshape(-1, 1, 2)], True, color, 1, cv2.LINE_AA)
            if pose.marker_centers_px:
                for marker_id, center in pose.marker_centers_px.items():
                    px, py = int(center[0]), int(center[1])
                    cv2.circle(image, (px, py), 3, (255, 255, 0), -1)
                    cv2.putText(
                        image, f"ID {marker_id}", (px + 4, py - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 0), 1, cv2.LINE_AA
                    )
            center = pose.cm_to_pixel(0, 0)
            x_end = pose.cm_to_pixel(4, 0)
            y_end = pose.cm_to_pixel(0, 4)
            if center is not None and x_end is not None:
                cv2.arrowedLine(
                    image, (int(center[0]), int(center[1])),
                    (int(x_end[0]), int(x_end[1])), (0, 0, 255), 1,
                    cv2.LINE_AA, tipLength=0.25
                )
            if center is not None and y_end is not None:
                cv2.arrowedLine(
                    image, (int(center[0]), int(center[1])),
                    (int(y_end[0]), int(y_end[1])), (0, 255, 0), 1,
                    cv2.LINE_AA, tipLength=0.25
                )
            sp = pose.cm_to_pixel(self.setpoint_x, self.setpoint_y)
            if sp is not None:
                x, y = int(sp[0]), int(sp[1])
                cv2.drawMarker(image, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 16, 1, cv2.LINE_AA)
                cv2.circle(image, (x, y), 7, (0, 0, 255), 1, cv2.LINE_AA)
        else:
            cv2.putText(
                image, "PLACA NO DETECTADA", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2, cv2.LINE_AA
            )

        if detection is not None and detection.found:
            center = (int(detection.cx), int(detection.cy))
            cv2.circle(
                image, center, max(4, int(detection.radius) + 3),
                (0, 255, 0), 2, cv2.LINE_AA
            )
            cv2.drawMarker(
                image, center, (0, 255, 0), cv2.MARKER_CROSS, 8, 1, cv2.LINE_AA
            )
            if ball_cm is not None:
                cv2.putText(
                    image, f"({ball_cm[0]:+.1f}, {ball_cm[1]:+.1f}) cm",
                    (center[0] + 7, center[1] - 7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 0), 1, cv2.LINE_AA
                )

    def _render_camera(self, frame, detection, ball_cm, pose):
        if frame is None:
            return
        image = frame.copy()
        self._draw_common_overlay(image, pose, detection, ball_cm)
        self._camera_frame_bgr = image
        self._redraw_camera()

    def _redraw_camera(self):
        if self._camera_frame_bgr is None or not hasattr(self, "camera_canvas"):
            return
        canvas = self.camera_canvas
        cw = max(160, canvas.winfo_width())
        ch = max(120, canvas.winfo_height())
        frame_h, frame_w = self._camera_frame_bgr.shape[:2]
        if frame_w <= 0 or frame_h <= 0:
            return
        scale = min(cw / frame_w, ch / frame_h)
        draw_w = max(1, int(frame_w * scale))
        draw_h = max(1, int(frame_h * scale))
        image = cv2.resize(
            self._camera_frame_bgr, (draw_w, draw_h), interpolation=cv2.INTER_AREA
        )
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self._photo = photo
        x = max(0, (cw - draw_w) // 2)
        y = max(0, (ch - draw_h) // 2)
        self._camera_rect = (x, y, draw_w, draw_h)
        if self._camera_item is None:
            self._camera_item = canvas.create_image(x, y, anchor=tk.NW, image=photo)
        else:
            canvas.itemconfigure(self._camera_item, image=photo)
            canvas.coords(self._camera_item, x, y)

    def _render_plate(self, ball_cm):
        canvas = self.plate_canvas
        canvas.delete("all")
        width = max(120, canvas.winfo_width())
        height = max(120, canvas.winfo_height())
        size = min(width, height)
        margin = size * 0.08
        scale = (size - 2 * margin) / (2 * self.position_limit_cm)
        offset_x = (width - size) / 2.0
        offset_y = (height - size) / 2.0
        center_x = offset_x + size / 2.0
        center_y = offset_y + size / 2.0
        left = center_x - self.position_limit_cm * scale
        top = center_y - self.position_limit_cm * scale
        right = center_x + self.position_limit_cm * scale
        bottom = center_y + self.position_limit_cm * scale
        canvas.create_rectangle(left, top, right, bottom, fill="#202020", outline="#00c8e0", width=2)
        for cm in (-6.0, 0.0, 6.0):
            x = center_x + cm * scale
            y = center_y - cm * scale
            canvas.create_line(x, top, x, bottom, fill="#343434")
            canvas.create_line(left, y, right, y, fill="#343434")
        for index, (cx, cy) in enumerate(self.config["plate"]["marker_centers_cm"]):
            x = center_x + float(cx) * scale
            y = center_y - float(cy) * scale
            canvas.create_rectangle(x - 7, y - 7, x + 7, y + 7, outline="#ffd000", width=1)
            canvas.create_text(x, y - 12, text=self.config["plate"]["marker_ids"][index],
                               fill="#ffd000", font=("Consolas", 8))
        canvas.create_oval(center_x - 5, center_y - 5, center_x + 5, center_y + 5,
                           outline="#777", width=1)
        if self.last_telemetry is not None:
            sign_x = -1.0 if self.invert_x else 1.0
            sign_y = -1.0 if self.invert_y else 1.0
            tilt_x = self.last_telemetry.tilt_x * sign_x
            tilt_y = self.last_telemetry.tilt_y * sign_y
            if abs(tilt_x) + abs(tilt_y) > 0.05:
                ex = center_x + tilt_x * scale * 1.2
                ey = center_y - tilt_y * scale * 1.2
                canvas.create_line(center_x, center_y, ex, ey, fill="#ff8c00", width=3, arrow=tk.LAST)
                canvas.create_text(ex + 6, ey, text="tilt", fill="#ff8c00",
                                   font=("Consolas", 8))
        point = ball_cm
        if point is None and self.last_telemetry is not None:
            sign_x = -1.0 if self.invert_x else 1.0
            sign_y = -1.0 if self.invert_y else 1.0
            point = (
                self.last_telemetry.x * sign_x,
                self.last_telemetry.y * sign_y,
            )
        if point is not None:
            bx = center_x + point[0] * scale
            by = center_y - point[1] * scale
            canvas.create_oval(bx - 10, by - 10, bx + 10, by + 10,
                               fill="#ff9f1a", outline="#fff", width=2)
        sx = center_x + self.setpoint_x * scale
        sy = center_y - self.setpoint_y * scale
        canvas.create_line(sx - 8, sy, sx + 8, sy, fill="#ff3030", width=2)
        canvas.create_line(sx, sy - 8, sx, sy + 8, fill="#ff3030", width=2)
        canvas.create_text(offset_x + 8, offset_y + 8, anchor=tk.NW, text="PLACA 24 x 24 cm",
                           fill="#00c8e0", font=("Consolas", 9))
        canvas.create_text(offset_x + 8, offset_y + size - 18, anchor=tk.NW,
                           text="+X derecha / +Y arriba",
                           fill="#777", font=("Consolas", 8))

    def _active_tab_name(self) -> str:
        try:
            return str(self.main_tabs.tab(self.main_tabs.select(), "text"))
        except (tk.TclError, AttributeError):
            return ""

    def _update_graphs(self):
        if not self.history:
            return
        now = time.perf_counter()
        if now - self.last_history < 0.15:
            return
        self.last_history = now
        start = now - 10.0
        values = [row for row in self.history if row[0] >= start]
        if not values:
            return
        x = [row[0] - now for row in values]
        self.line_ex.set_data(x, [row[1] for row in values])
        self.line_ey.set_data(x, [row[2] for row in values])
        self.line_tx.set_data(x, [row[3] for row in values])
        self.line_ty.set_data(x, [row[4] for row in values])
        self.line_sx.set_data(x, [row[5] for row in values])
        self.line_sy.set_data(x, [row[6] for row in values])
        if hasattr(self, "line_sx_sep"):
            self.line_sx_sep.set_data(x, [row[5] for row in values])
            self.line_sy_sep.set_data(x, [row[6] for row in values])
        for axis, low, high in (
            (self.ax_err, -13, 13),
            (self.ax_tilt, -9, 9),
            (self.ax_servo, 54, 126),
        ):
            axis.set_xlim(-10, 0)
            axis.set_ylim(low, high)
        if hasattr(self, "ax_sx"):
            self.ax_sx.set_xlim(-10, 0)
            self.ax_sx.set_ylim(54, 126)
            self.ax_sy.set_xlim(-10, 0)
            self.ax_sy.set_ylim(54, 126)
        active = self._active_tab_name()
        if active == "Gráficas":
            self.graph_canvas.draw_idle()
        elif active == "Servos X/Y separados" and hasattr(self, "servo_canvas"):
            self.servo_canvas.draw_idle()

    # ------------------------------------------------------------------ datos ---
    def _log(self, text: str):
        if not hasattr(self, "log_text"):
            return
        if self._active_tab_name() != "Datos":
            return
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 80:
            self.log_text.delete("1.0", "20.0")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _show_help(self):
        messagebox.showinfo(
            "Ayuda rápida",
            "PID EN VIVO (Kp, Ki, Kd)\n"
            "Son las tres ganancias del controlador, no son drivers ni cámaras.\n\n"
            "Kp: corrige según el error actual.\n"
            "Ki: suma el error acumulado; elimina el error de largo plazo.\n"
            "Kd: frena los cambios bruscos y las oscilaciones.\n\n"
            "Se aplican al instante al ESP32 con G,B. Si los valores son muy altos, "
            "la placa oscila. Empezá con Kp=0.50, Ki=0.02, Kd=0.33.\n\n"
            "GUARDAR AJUSTES EN EL ESP32\n"
            "Guarda Kp, Ki, Kd y los offsets de centro en la memoria interna (NVS) "
            "del ESP32. No instala el driver USB ni la cámara.\n\n"
            "INVERTIR SERVO X / Y\n"
            "Si un eje tira al revés, marcá su casilla. La PC espeja las "
            "coordenadas en el software: no hay que recompilar el firmware.\n\n"
            "CÁMARA Y PUERTO USB\n"
            "Abre el selector de cámara/URL y COM. El driver CH340/CP210x y la app "
            "DroidCam/Iriun/IP Webcam se instalan aparte, en Windows.",
            parent=self.root,
        )

    def _on_invert_change(self):
        self.invert_x = bool(self.invert_x_var.get())
        self.invert_y = bool(self.invert_y_var.get())
        self.config["control"]["invert_x"] = self.invert_x
        self.config["control"]["invert_y"] = self.invert_y
        servo = self.config["simulation"]["servo"]
        servo["invert_x"] = self.invert_x
        servo["invert_y"] = self.invert_y
        if self.sim is not None:
            self.sim.fake.servo_config["invert_x"] = self.invert_x
            self.sim.fake.servo_config["invert_y"] = self.invert_y
        try:
            save_config(self.config, self.config_path)
        except OSError:
            pass
        self._send_setpoint()
        self.message_var.set(
            f"Inversión de software: X={'ON' if self.invert_x else 'OFF'}, "
            f"Y={'ON' if self.invert_y else 'OFF'}. No hace falta recompilar."
        )

    # ------------------------------------------------------------- acciones ---
    def _save(self):
        self.config["control"]["pid"]["kp"] = self.gains["kp"]
        self.config["control"]["pid"]["ki"] = self.gains["ki"]
        self.config["control"]["pid"]["kd"] = self.gains["kd"]
        self.config["control"]["setpoint_x_cm"] = self.setpoint_x
        self.config["control"]["setpoint_y_cm"] = self.setpoint_y
        self.config["control"]["invert_x"] = self.invert_x
        self.config["control"]["invert_y"] = self.invert_y
        servo = self.config["simulation"]["servo"]
        servo["invert_x"] = self.invert_x
        servo["invert_y"] = self.invert_y
        try:
            save_config(self.config, self.config_path)
        except OSError as exc:
            self.message_var.set(f"No se pudo guardar config.json: {exc}")
            return
        self.link.send("W")
        self.message_var.set("Guardado enviado al ESP32 y a config.json")

    def _calibrate_color(self):
        if self.last_frame is None or self.last_pose is None or not self.last_pose.valid:
            self.message_var.set("Necesitás placa y cámara para calibrar el color.")
            return
        from calibration import calibrate_hsv

        mask = self.last_pose.plate_mask(self.last_frame.shape)
        result = calibrate_hsv(self.last_frame, self.config["vision"], plate_mask=mask)
        if result is None:
            self.message_var.set("Calibración de color cancelada.")
            return
        self.config["vision"] = result
        try:
            save_config(self.config, self.config_path)
        except OSError as exc:
            self.message_var.set(f"No se pudo guardar el color: {exc}")
            return
        self.message_var.set("Color HSV guardado en config.json")

    def _configure_devices(self):
        try:
            applied = setup_devices(self.config, self.config_path)
        except Exception as exc:
            self.message_var.set(f"No se pudo abrir el selector: {exc}")
            return
        if not applied:
            self.message_var.set("Configuración de dispositivos cancelada.")
            return
        self.message_var.set("Dispositivos guardados. Reiniciando...")
        self._restart()

    def _restart(self):
        try:
            subprocess.Popen([sys.executable, *sys.argv], cwd=str(ROOT))
        except Exception as exc:
            self.message_var.set(f"No se pudo reiniciar: {exc}")
            return
        self.close()

    def close(self):
        if self._closing:
            return
        self._closing = True
        try:
            self.link.send(format_mode(0))
            time.sleep(0.05)
        except Exception:
            pass
        if self.camera is not None:
            self.camera.stop()
        try:
            self.link.close()
        except Exception:
            pass
        if self.logger is not None:
            self.logger.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def run_tk(args) -> int:
    """Punto de entrada de la interfaz Tkinter."""
    ensure_default_config()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)

    if args.setup_devices:
        applied = setup_devices(config, config_path)
        return 0 if applied else 1

    if (
        not args.sim
        and args.camera is None
        and args.port is None
        and not bool(config.get("setup_completed", False))
    ):
        try:
            setup_devices(config, config_path)
        except Exception as exc:
            print(f"[tk] No se pudo abrir el selector inicial: {exc}")

    simulation_mode = bool(args.sim)
    camera = None
    sim = None
    if simulation_mode:
        sim = Simulation(config)
        sim.start()
        link = sim.link
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
    except OSError:
        logger = TelemetryLogger(log_directory, enabled=False)

    root = tk.Tk()
    app = TkApp(root, config, config_path, link, camera, sim, logger, simulation_mode)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.close()
    finally:
        if not app._closing:
            app.close()
    return 0


def main(argv=None) -> int:
    return run_tk(_parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
