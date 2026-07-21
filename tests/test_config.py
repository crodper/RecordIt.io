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


def test_carpeta_datos_defecto_y_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.carpeta_datos() is None
    config.guardar({"carpeta_datos": "/data/recordit"})
    assert config.carpeta_datos() == "/data/recordit"


def test_gitlab_token_defecto_y_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.gitlab_token() is None
    config.guardar({"gitlab_token": "glpat-xxx"})
    assert config.gitlab_token() == "glpat-xxx"


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


def test_reunion_online_defecto_y_persiste(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.reunion_online() is False
    config.guardar_reunion_online(True)
    assert config.reunion_online() is True
    # No pisa otras claves.
    config.guardar_microfono("Mic X")
    config.guardar_reunion_online(False)
    assert config.reunion_online() is False
    assert config.microfono() == "Mic X"


def test_proveedor_defecto_es_claude(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.proveedor() == "claude"
    assert config.openai_api_key() is None
    assert config.modelo_openai() == "gpt-5"


def test_config_openai_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config.guardar({"proveedor": "openai", "openai_api_key": "sk-oa",
                    "modelo_openai": "gpt-5-mini"})
    assert config.proveedor() == "openai"
    assert config.openai_api_key() == "sk-oa"
    assert config.modelo_openai() == "gpt-5-mini"
