"""Carga y guardado simple de config.json, sin dependencias extra."""

from __future__ import annotations

import json
from pathlib import Path

PC_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PC_DIR / "config.json"


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
