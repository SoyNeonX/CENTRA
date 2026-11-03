import json

import pytest

from config import load_config, save_config
from devices import (
    AUTO_PORT,
    apply_device_config,
    normalize_camera_source,
)


def test_normaliza_indices_y_urls():
    assert normalize_camera_source(2) == 2
    assert normalize_camera_source("3") == 3
    assert normalize_camera_source("http://192.168.0.2:8080/video") == (
        "http://192.168.0.2:8080/video"
    )
    assert normalize_camera_source("rtsp://camara/video") == "rtsp://camara/video"
    with pytest.raises(ValueError):
        normalize_camera_source("camara-1")
    with pytest.raises(ValueError):
        normalize_camera_source("")
    with pytest.raises(ValueError):
        normalize_camera_source(-1)


def test_config_camara_y_puerto_automatico():
    config = load_config()
    updated = apply_device_config(config, 1, AUTO_PORT)
    assert updated["camera"]["source"] == 1
    assert updated["serial"]["port"] == ""
    assert updated["serial"]["auto_detect"] is True
    assert updated["setup_completed"] is True
    # La configuración original no se modifica hasta que la GUI la acepta.
    assert config["camera"]["source"] == 0


def test_config_camara_url_y_puerto_fijo():
    config = load_config()
    updated = apply_device_config(
        config, "http://192.168.0.50:8080/video", "COM7"
    )
    assert updated["camera"]["source"] == "http://192.168.0.50:8080/video"
    assert updated["serial"]["port"] == "COM7"
    assert updated["serial"]["auto_detect"] is False


def test_guardado_json_es_valido(tmp_path):
    config = load_config()
    updated = apply_device_config(config, 2, AUTO_PORT)
    path = tmp_path / "config.json"
    save_config(updated, path)
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    assert data["camera"]["source"] == 2
    assert data["setup_completed"] is True
