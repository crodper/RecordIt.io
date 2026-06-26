from recordit import config


def test_guardar_y_cargar_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config.guardar({"api_key": "sk-test", "modelo_acta": "claude-sonnet-4-6"})
    assert config.api_key() == "sk-test"
    assert config.modelo_acta() == "claude-sonnet-4-6"


def test_defaults_sin_fichero(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.api_key() is None
    assert config.modelo_acta() == "claude-opus-4-8"


def test_microfono_persiste(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.microfono() is None
    config.guardar_microfono("Mic interno")
    assert config.microfono() == "Mic interno"
    # No pisa otras claves.
    config.guardar({**config.cargar(), "modelo_acta": "claude-sonnet-4-6"})
    config.guardar_microfono("Otro mic")
    assert config.modelo_acta() == "claude-sonnet-4-6"
    assert config.microfono() == "Otro mic"
