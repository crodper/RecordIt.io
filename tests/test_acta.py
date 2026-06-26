import subprocess
from types import SimpleNamespace

from recordit import acta


def test_construir_prompt_incluye_reglas():
    prompt = acta.construir_prompt("texto de la reunión", fecha="16 de junio de 2026", base="reunion_x")
    assert "ACTA DE REUNIÓN" in prompt
    assert "front-matter" in prompt
    assert "(dudoso)" in prompt
    assert "texto de la reunión" in prompt


def test_construir_prompt_inyecta_glosario():
    prompt = acta.construir_prompt("acta sobre el modbus", fecha="16 de junio de 2026", base="reunion_x")
    # el bloque de vocabulario va antes de la transcripción y lista términos canónicos
    assert "Vocabulario propio de la organización" in prompt
    assert "Modbus" in prompt
    # el bloque va antes del marcador real de la transcripción (rindex: última aparición,
    # la primera está en una instrucción del propio prompt)
    assert prompt.index("Vocabulario propio") < prompt.rindex("=== TRANSCRIPCIÓN ===")


def test_construir_prompt_sin_glosario_no_pone_seccion(monkeypatch):
    monkeypatch.setattr(acta.glosario, "bloque_prompt", lambda: "")
    prompt = acta.construir_prompt("texto", fecha="16 de junio de 2026", base="reunion_x")
    assert "Vocabulario propio de la organización" not in prompt
    assert "ACTA DE REUNIÓN" in prompt  # el resto del prompt sigue intacto


def test_limpiar_markdown_quita_fences():
    crudo = "```markdown\n---\ntitle: X\n---\ncuerpo\n```"
    limpio = acta._limpiar_markdown(crudo)
    assert limpio.startswith("---")
    assert "```" not in limpio


def test_redactar_acta_usa_api_mockeada(monkeypatch):
    capturado = {}

    class _Mensajes:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="---\ntitle: A\n---\nok")])

    class _ClienteFake:
        def __init__(self, api_key=None):
            capturado["api_key"] = api_key
            self.messages = _Mensajes()

    monkeypatch.setattr(acta.anthropic, "Anthropic", _ClienteFake)
    md = acta.redactar_acta("transcripcion", fecha="16 de junio de 2026",
                            base="reunion_x", api_key="sk-test", modelo="claude-opus-4-8")
    assert md.startswith("---")
    assert capturado["api_key"] == "sk-test"
    assert capturado["model"] == "claude-opus-4-8"


def test_redactar_acta_via_cli_mockeada(monkeypatch):
    capturado = {}

    def _run_fake(cmd, **kwargs):
        capturado["cmd"] = cmd
        capturado["input"] = kwargs.get("input")
        return SimpleNamespace(stdout="```markdown\n---\ntitle: A\n---\nok\n```", returncode=0)

    monkeypatch.setattr(acta.claude_auth, "ruta_cli", lambda: "claude")
    monkeypatch.setattr(acta.subprocess, "run", _run_fake)
    md = acta.redactar_acta("transcripcion-larga", fecha="16 de junio de 2026",
                            base="reunion_x", metodo="cli")
    assert md.startswith("---")
    assert "```" not in md
    assert capturado["cmd"] == ["claude", "-p"]          # ruta resuelta + -p
    assert "transcripcion-larga" in capturado["input"]   # prompt por stdin


def _raise_called_process_error(stderr):
    def _run_fake(cmd, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="", stderr=stderr)
    return _run_fake


def test_redactar_cli_sin_login_da_mensaje_accionable(monkeypatch):
    monkeypatch.setattr(acta.claude_auth, "ruta_cli", lambda: "claude")
    monkeypatch.setattr(
        acta.subprocess, "run",
        _raise_called_process_error("Invalid API key · Please run /login"))
    try:
        acta.redactar_acta("t", fecha="16 de junio de 2026", base="r", metodo="cli")
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError as exc:
        assert "claude login" in str(exc)


def test_redactar_cli_error_generico_propaga_stderr(monkeypatch):
    monkeypatch.setattr(acta.claude_auth, "ruta_cli", lambda: "claude")
    monkeypatch.setattr(
        acta.subprocess, "run",
        _raise_called_process_error("kaboom interno del cli"))
    try:
        acta.redactar_acta("t", fecha="16 de junio de 2026", base="r", metodo="cli")
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError as exc:
        assert "kaboom interno del cli" in str(exc)
        assert "claude login" not in str(exc)
