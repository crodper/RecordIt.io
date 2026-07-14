import json
import subprocess
import urllib.error
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


def test_redactar_acta_openai_mockeado(monkeypatch):
    capturado = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "---\ntitle: A\n---\nok"}}]}
            ).encode("utf-8")

    def _urlopen_fake(req, *a, **k):
        capturado["url"] = req.full_url
        capturado["auth"] = req.headers.get("Authorization")
        capturado["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr(acta.urllib.request, "urlopen", _urlopen_fake)
    md = acta.redactar_acta("transcripcion-openai", fecha="16 de junio de 2026",
                            base="reunion_x", proveedor="openai",
                            api_key="sk-oa", modelo="gpt-5")
    assert md.startswith("---")
    assert "```" not in md
    assert capturado["url"] == acta.URL_OPENAI
    assert capturado["auth"] == "Bearer sk-oa"
    assert capturado["body"]["model"] == "gpt-5"
    assert capturado["body"]["max_completion_tokens"] == acta.MAX_TOKENS_OPENAI
    assert "transcripcion-openai" in capturado["body"]["messages"][0]["content"]


def test_redactar_openai_401_da_mensaje_accionable(monkeypatch):
    def _urlopen_fake(req, *a, **k):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(acta.urllib.request, "urlopen", _urlopen_fake)
    try:
        acta.redactar_acta("t", fecha="16 de junio de 2026", base="r",
                           proveedor="openai", api_key="mala", modelo="gpt-5")
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError as exc:
        assert "OpenAI" in str(exc)
        assert "Ajustes" in str(exc)


def test_redactar_openai_respuesta_vacia_da_error(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": []}).encode("utf-8")

    monkeypatch.setattr(acta.urllib.request, "urlopen", lambda req, *a, **k: _Resp())
    try:
        acta.redactar_acta("t", fecha="16 de junio de 2026", base="r",
                           proveedor="openai", api_key="sk-oa", modelo="gpt-5")
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError as exc:
        assert "vacía o inesperada" in str(exc)


def test_redactar_openai_truncada_da_error(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"finish_reason": "length",
                              "message": {"content": "x"}}]}
            ).encode("utf-8")

    monkeypatch.setattr(acta.urllib.request, "urlopen", lambda req, *a, **k: _Resp())
    try:
        acta.redactar_acta("t", fecha="16 de junio de 2026", base="r",
                           proveedor="openai", api_key="sk-oa", modelo="gpt-5")
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError as exc:
        assert "por longitud" in str(exc)


def test_error_openai_http_no_401(monkeypatch):
    def _urlopen_fake(req, *a, **k):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(acta.urllib.request, "urlopen", _urlopen_fake)
    try:
        acta.redactar_acta("t", fecha="16 de junio de 2026", base="r",
                           proveedor="openai", api_key="sk-oa", modelo="gpt-5")
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError as exc:
        assert "500" in str(exc)


def test_error_openai_conexion(monkeypatch):
    def _urlopen_fake(req, *a, **k):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(acta.urllib.request, "urlopen", _urlopen_fake)
    try:
        acta.redactar_acta("t", fecha="16 de junio de 2026", base="r",
                           proveedor="openai", api_key="sk-oa", modelo="gpt-5")
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError as exc:
        assert "No se pudo conectar con OpenAI" in str(exc)


def test_redactar_openai_pasa_timeout(monkeypatch):
    capturado = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "---\ntitle: A\n---\nok"}}]}
            ).encode("utf-8")

    def _urlopen_fake(req, *a, **k):
        capturado["timeout"] = k.get("timeout")
        return _Resp()

    monkeypatch.setattr(acta.urllib.request, "urlopen", _urlopen_fake)
    acta.redactar_acta("t", fecha="16 de junio de 2026", base="r",
                       proveedor="openai", api_key="sk-oa", modelo="gpt-5")
    assert capturado["timeout"] == acta.TIMEOUT_OPENAI
