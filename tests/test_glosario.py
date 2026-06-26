from recordit import glosario


def test_repo_trae_terminos_ejemplo():
    ts = glosario.terminos()
    assert "Modbus" in ts
    assert "KNX" in ts


def test_hotwords_es_string_separado_por_comas():
    hw = glosario.hotwords()
    assert isinstance(hw, str)
    assert "Modbus" in hw
    assert ", " in hw


def test_usuario_se_anade_y_no_duplica(monkeypatch, tmp_path):
    glosario_usuario = tmp_path / "glosario.txt"
    glosario_usuario.write_text(
        "# comentario\n\nTerminoNuevo\nmodbus\n", encoding="utf-8")
    monkeypatch.setattr(
        glosario.config, "ruta_glosario_usuario", lambda: glosario_usuario)

    ts = glosario.terminos()
    assert "TerminoNuevo" in ts                       # término nuevo del usuario
    assert ts.count("Modbus") == 1                     # "modbus" no duplica a "Modbus"
    assert "modbus" not in ts                          # se conserva la forma del repo


def test_glosario_vacio_devuelve_none(monkeypatch, tmp_path):
    vacio = tmp_path / "vacio.txt"
    monkeypatch.setattr(glosario, "_RUTA_REPO", vacio)
    monkeypatch.setattr(
        glosario.config, "ruta_glosario_usuario", lambda: vacio)
    assert glosario.hotwords() is None


def test_bloque_prompt_lista_terminos():
    bloque = glosario.bloque_prompt()
    assert "NORMALÍZALO" in bloque
    assert "Modbus" in bloque


def test_bloque_prompt_vacio_si_no_hay_terminos(monkeypatch, tmp_path):
    vacio = tmp_path / "vacio.txt"
    monkeypatch.setattr(glosario, "_RUTA_REPO", vacio)
    monkeypatch.setattr(
        glosario.config, "ruta_glosario_usuario", lambda: vacio)
    assert glosario.bloque_prompt() == ""
