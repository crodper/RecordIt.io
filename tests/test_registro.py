import logging

from recordit import registro


def test_ruta_log_bajo_base_datos(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    assert registro.ruta_log() == tmp_path / "recordit.log"


def test_configurar_endereza_stdout_y_stderr_nulos(monkeypatch, tmp_path):
    # En modo --windowed (PyInstaller) sys.stdout/stderr son None; librerías que
    # escriben progreso (tqdm, huggingface_hub) reventarían. configurar() debe
    # dejar flujos escribibles que no lancen excepción.
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(registro.sys, "stdout", None)
    monkeypatch.setattr(registro.sys, "stderr", None)
    registro.configurar()
    assert registro.sys.stdout is not None
    assert registro.sys.stderr is not None
    registro.sys.stdout.write("progreso 10%\n")   # no debe lanzar
    registro.sys.stderr.write("aviso\n")           # no debe lanzar
    registro.sys.stdout.flush()


def test_registrar_excepcion_escribe_traceback(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    registro.configurar()
    try:
        raise ValueError("boom de prueba")
    except ValueError as exc:
        ruta = registro.registrar_excepcion(f"fallo: {exc}")
    logging.shutdown()
    contenido = ruta.read_text(encoding="utf-8")
    assert "boom de prueba" in contenido
    assert "ValueError" in contenido
    assert "Traceback" in contenido
