"""
Gráfico opcional de un CSV generado por logger.py.

Uso:
    python tools/plot_log.py logs/telemetria_20260101_120000.csv
    python tools/plot_log.py logs/telemetria_....csv --save grafico.png

Requiere matplotlib (está en requirements.txt como dependencia opcional).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def load_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("El CSV está vacío")
        columns = {
            name: [] for name in ("tiempo_s", "x", "y", "err_x", "err_y", "tilt_x", "tilt_y", "estado")
        }
        for row in reader:
            for name, values in columns.items():
                values.append(float(row[name]))
    return columns


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Graficar telemetría CSV")
    parser.add_argument("csv_file", help="archivo CSV de pc/logs")
    parser.add_argument("--save", default=None, help="guardar el gráfico en un PNG")
    args = parser.parse_args(argv)

    path = Path(args.csv_file)
    if not path.is_file():
        print(f"No existe {path}")
        return 2

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Falta matplotlib. Instalalo con: pip install matplotlib")
        return 3

    data = load_csv(path)
    time_values = data["tiempo_s"]

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    axes[0].plot(time_values, data["x"], label="x")
    axes[0].plot(time_values, data["y"], label="y")
    axes[0].axhline(0, color="gray", linewidth=0.8)
    axes[0].set_ylabel("posicion normalizada")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title("Plataforma estabilizadora de pelota")

    axes[1].plot(time_values, data["err_x"], label="error x")
    axes[1].plot(time_values, data["err_y"], label="error y")
    axes[1].set_ylabel("error")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(time_values, data["tilt_x"], label="tilt x")
    axes[2].plot(time_values, data["tilt_y"], label="tilt y")
    axes[2].set_ylabel("inclinacion (grados)")
    axes[2].set_xlabel("tiempo (s)")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    if args.save:
        output = Path(args.save)
        fig.savefig(output, dpi=130)
        print(f"Gráfico guardado en {output.resolve()}")
    else:
        try:
            plt.show()
        except Exception as exc:
            print(f"No se pudo abrir la ventana de matplotlib: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
