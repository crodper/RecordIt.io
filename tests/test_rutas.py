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


def test_estado_reunion_sin_transcribir(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    assert rutas.estado_reunion("reunion_x") == "sin_transcribir"
    # no debe crear la carpeta solo por consultar el estado
    assert not (tmp_path / "transcripciones" / "reunion_x").exists()


def test_estado_reunion_generando_gana(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    rutas.ruta_acta_md("reunion_x").write_text("x", encoding="utf-8")  # crea la carpeta
    assert rutas.estado_reunion("reunion_x", generando=True) == "generando"


def test_estado_reunion_transcrita(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    rutas.ruta_transcripcion("reunion_x").write_text("hola", encoding="utf-8")
    assert rutas.estado_reunion("reunion_x") == "transcrita"


def test_estado_reunion_con_acta_gana_a_transcrita(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    rutas.ruta_transcripcion("reunion_x").write_text("hola", encoding="utf-8")
    rutas.ruta_acta_md("reunion_x", "2026-07-13").write_text("# acta", encoding="utf-8")
    assert rutas.estado_reunion("reunion_x") == "con_acta"


def test_nombre_import_libre_sin_colision(tmp_path):
    assert rutas.nombre_import_libre("/algun/sitio/charla.m4a", tmp_path) == "charla.m4a"


def test_nombre_import_libre_una_colision(tmp_path):
    (tmp_path / "charla.m4a").write_bytes(b"")
    assert rutas.nombre_import_libre("charla.m4a", tmp_path) == "charla (2).m4a"


def test_nombre_import_libre_varias_colisiones(tmp_path):
    (tmp_path / "charla.m4a").write_bytes(b"")
    (tmp_path / "charla (2).m4a").write_bytes(b"")
    assert rutas.nombre_import_libre("charla.m4a", tmp_path) == "charla (3).m4a"
