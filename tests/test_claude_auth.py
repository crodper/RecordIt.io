from recordit import claude_auth, config


def _config_temporal(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))


def _sin_cli_en_disco(monkeypatch):
    """Neutraliza la búsqueda de claude en el PATH y en ubicaciones del disco."""
    monkeypatch.setattr(claude_auth.shutil, "which", lambda n: None)
    monkeypatch.setattr(claude_auth.os.path, "isfile", lambda p: False)


def test_detectar_cli(monkeypatch):
    monkeypatch.setattr(claude_auth.shutil, "which", lambda n: "/usr/bin/claude")
    assert claude_auth.detectar() == ("cli", None)


def test_detectar_api_por_entorno(monkeypatch):
    _sin_cli_en_disco(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-entorno")
    assert claude_auth.detectar() == ("api", "sk-entorno")


def test_detectar_nada(monkeypatch):
    _sin_cli_en_disco(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert claude_auth.detectar() == (None, None)


def test_conectar_persiste_cli(monkeypatch, tmp_path):
    _config_temporal(monkeypatch, tmp_path)
    monkeypatch.setattr(claude_auth.shutil, "which", lambda n: "/usr/bin/claude")
    metodo, _ = claude_auth.conectar()
    assert metodo == "cli"
    assert config.cargar()["metodo"] == "cli"
    assert claude_auth.conectado() is True
    assert claude_auth.estado() == ("cli", None)


def test_conectado_falso_si_cli_desaparece(monkeypatch, tmp_path):
    _config_temporal(monkeypatch, tmp_path)
    config.guardar({"metodo": "cli"})
    _sin_cli_en_disco(monkeypatch)  # claude ya no está ni en PATH ni en disco
    assert claude_auth.conectado() is False
