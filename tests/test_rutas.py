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
    assert rutas.base_desde_audio("/x/reunion_2026.m4a") == "reunion_2026"


def test_listar_grabaciones_incluye_m4a_y_descarta_otros(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    grab = rutas.dir_grabaciones()
    (grab / "reunion.wav").write_bytes(b"")
    (grab / "movil.m4a").write_bytes(b"")
    (grab / "voz.mp3").write_bytes(b"")
    (grab / "notas.txt").write_bytes(b"")  # no es audio: se ignora

    nombres = {p.name for p in rutas.listar_grabaciones()}
    assert nombres == {"reunion.wav", "movil.m4a", "voz.mp3"}


def test_listar_grabaciones_ordena_por_fecha(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    grab = rutas.dir_grabaciones()
    antiguo = grab / "antiguo.wav"
    reciente = grab / "reciente.m4a"
    antiguo.write_bytes(b"")
    reciente.write_bytes(b"")
    os.utime(antiguo, (1000, 1000))
    os.utime(reciente, (2000, 2000))

    assert [p.name for p in rutas.listar_grabaciones()] == ["reciente.m4a", "antiguo.wav"]
