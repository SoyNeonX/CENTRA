"""Carga y guardado simple de config.json, sin dependencias extra."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PC_DIR = Path(__file__).resolve().parent


def app_dir() -> Path:
    """Carpeta escribible de la app: la del .exe o pc/ en modo desarrollo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PC_DIR


DEFAULT_CONFIG_PATH = app_dir() / "config.json"


def ensure_default_config() -> Path:
    """
    En el .exe, config.json se copia junto al ejecutable la primera vez.
    En desarrollo ya existe en pc/config.json.
    """
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    bundled = Path(getattr(sys, "_MEIPASS", PC_DIR)) / "config.json"
    if bundled.exists() and bundled.resolve() != DEFAULT_CONFIG_PATH.resolve():
        shutil.copy2(bundled, DEFAULT_CONFIG_PATH)
        return DEFAULT_CONFIG_PATH
    raise FileNotFoundError(
        f"No se encontro config.json y no hay una copia incluida: {DEFAULT_CONFIG_PATH}"
    )


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config, dict):
        raise ValueError("config.json debe contener un objeto JSON")
    return config


def save_config(config: dict, path: str | Path | None = None) -> Path:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(config, file, indent=2, ensure_ascii=False)
        file.write("\n")
    temporary.replace(config_path)
    return config_path
