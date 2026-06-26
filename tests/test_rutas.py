import os
from pathlib import Path

from recordit import rutas


def test_base_datos_usa_override(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    assert rutas.base_datos() == tmp_path


def test_rutas_reunion_nombres_cortos(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    base = "reunion_2026-06-16_10-06-12"
    assert rutas.ruta_transcripcion(base) == tmp_path / "transcripciones" / base / "transcripcion.txt"
    assert rutas.ruta_timestamps(base) == tmp_path / "transcripciones" / base / "transcripcion_timestamps.txt"
    assert rutas.ruta_acta_md(base) == tmp_path / "transcripciones" / base / "acta.md"
    assert rutas.ruta_clean(base) == tmp_path / "transcripciones" / base / "clean_16k.wav"


def test_dir_grabaciones_se_crea(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    d = rutas.dir_grabaciones()
    assert d.is_dir()
    assert d == tmp_path / "grabaciones"


def test_base_desde_audio():
    assert rutas.base_desde_audio("/x/reunion_2026.wav") == "reunion_2026"
