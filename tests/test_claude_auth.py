import subprocess

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


def test_comando_instalacion_windows(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "nt")
    assert claude_auth.comando_instalacion() == "irm https://claude.ai/install.ps1 | iex"


def test_comando_instalacion_linux(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    assert claude_auth.comando_instalacion() == (
        "curl -fsSL https://claude.ai/install.sh | bash")


def test_url_ayuda_apunta_a_la_guia_de_instalacion():
    assert claude_auth.URL_AYUDA == (
        "https://code.claude.com/docs/es/setup#native-install-recommended")


class _Res:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _capturar_run(monkeypatch, resultado):
    """Sustituye subprocess.run y guarda el argv con el que se le llamó."""
    visto = {}

    def _run_fake(argv, **kwargs):
        visto["argv"] = argv
        visto["kwargs"] = kwargs
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(claude_auth.subprocess, "run", _run_fake)
    return visto


def _capturar_popen(monkeypatch):
    visto = {}

    def _popen_fake(argv, **kwargs):
        visto["argv"] = argv
        return object()

    monkeypatch.setattr(claude_auth.subprocess, "Popen", _popen_fake)
    return visto


def test_instalar_windows_usa_powershell(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "nt")
    visto = _capturar_run(monkeypatch, _Res(0, stdout="instalado"))
    ok, salida = claude_auth.instalar()
    assert ok is True
    assert "instalado" in salida
    assert visto["argv"] == [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", "irm https://claude.ai/install.ps1 | iex"]


def test_instalar_linux_usa_bash(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    visto = _capturar_run(monkeypatch, _Res(0))
    ok, _salida = claude_auth.instalar()
    assert ok is True
    # -o pipefail: sin él, `curl ... | bash` con la red caída sale con 0 (el
    # código de salida es el de bash, no el de curl) y el fallo pasa inadvertido.
    assert visto["argv"] == [
        "bash", "-o", "pipefail", "-c",
        "curl -fsSL https://claude.ai/install.sh | bash"]


def test_instalar_pasa_timeout_y_nunca_shell(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    visto = _capturar_run(monkeypatch, _Res(0))
    claude_auth.instalar()
    assert visto["kwargs"]["timeout"] == claude_auth.TIMEOUT_INSTALACION
    assert "shell" not in visto["kwargs"]
    assert visto["kwargs"]["stdin"] == subprocess.DEVNULL
    # En Linux no aplica el flag de Windows para no abrir consola.
    assert "creationflags" not in visto["kwargs"]


def test_instalar_windows_no_abre_ventana_de_consola(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "nt")
    visto = _capturar_run(monkeypatch, _Res(0))
    claude_auth.instalar()
    assert "creationflags" in visto["kwargs"]


def test_instalar_fallo_devuelve_salida(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    _capturar_run(monkeypatch, _Res(1, stderr="no hay red"))
    ok, salida = claude_auth.instalar()
    assert ok is False
    assert "no hay red" in salida


def test_instalar_timeout_no_propaga(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    _capturar_run(monkeypatch, subprocess.TimeoutExpired(cmd="bash", timeout=300))
    ok, salida = claude_auth.instalar()
    assert ok is False
    assert "demasiado" in salida


def test_instalar_sin_interprete_no_propaga(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "nt")
    _capturar_run(monkeypatch, OSError("no existe powershell"))
    ok, salida = claude_auth.instalar()
    assert ok is False
    assert "no existe powershell" in salida


def test_abrir_login_sin_cli_devuelve_false(monkeypatch):
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: None)
    assert claude_auth.abrir_login() is False


def test_abrir_login_windows_abre_consola(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "nt")
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: r"C:\claude.exe")
    visto = _capturar_popen(monkeypatch)
    assert claude_auth.abrir_login() is True
    assert visto["argv"] == ["cmd", "/c", "start", "", "cmd", "/k",
                             r"C:\claude.exe", "auth", "login"]


def test_abrir_login_linux_usa_el_primer_terminal(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/home/u/.local/bin/claude")
    monkeypatch.setattr(claude_auth.shutil, "which",
                        lambda n: "/usr/bin/konsole" if n == "konsole" else None)
    visto = _capturar_popen(monkeypatch)
    assert claude_auth.abrir_login() is True
    assert visto["argv"] == ["konsole", "-e", "/home/u/.local/bin/claude",
                             "auth", "login"]


def test_abrir_login_gnome_terminal_usa_doble_guion(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/home/u/.local/bin/claude")
    monkeypatch.setattr(claude_auth.shutil, "which",
                        lambda n: "/usr/bin/gnome-terminal" if n == "gnome-terminal" else None)
    visto = _capturar_popen(monkeypatch)
    assert claude_auth.abrir_login() is True
    assert visto["argv"] == ["gnome-terminal", "--", "/home/u/.local/bin/claude",
                             "auth", "login"]


def test_abrir_login_macos_abre_terminal_con_osascript(monkeypatch):
    # En macOS no hay gnome-terminal/konsole: se le pide a Terminal.app que
    # ejecute el login con AppleScript.
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    monkeypatch.setattr(claude_auth.sys, "platform", "darwin")
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/Users/u/.local/bin/claude")
    visto = _capturar_popen(monkeypatch)
    assert claude_auth.abrir_login() is True
    argv = visto["argv"]
    assert argv[0] == "osascript"
    assert argv[2] == ('tell application "Terminal" to do script '
                       '"/Users/u/.local/bin/claude auth login"')
    assert "activate" in argv[-1]


def test_abrir_login_macos_entrecomilla_rutas_con_espacios(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    monkeypatch.setattr(claude_auth.sys, "platform", "darwin")
    monkeypatch.setattr(claude_auth, "ruta_cli",
                        lambda: "/Users/u/Application Support/claude")
    visto = _capturar_popen(monkeypatch)
    assert claude_auth.abrir_login() is True
    # La ruta va entrecomillada para el shell: sin esto, Terminal partiría el
    # comando en el espacio y el login no arrancaría.
    assert "'/Users/u/Application Support/claude' auth login" in visto["argv"][2]


def test_abrir_login_linux_sin_terminal_devuelve_false(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "posix")
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/home/u/.local/bin/claude")
    monkeypatch.setattr(claude_auth.shutil, "which", lambda n: None)
    assert claude_auth.abrir_login() is False


def test_abrir_login_fallo_al_lanzar_devuelve_false(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "nt")
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: r"C:\claude.exe")

    def _popen_roto(argv, **kwargs):
        raise OSError("sin consola")

    monkeypatch.setattr(claude_auth.subprocess, "Popen", _popen_roto)
    assert claude_auth.abrir_login() is False


def test_sesion_iniciada_sin_cli_devuelve_false(monkeypatch):
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: None)
    assert claude_auth.sesion_iniciada() is False


def test_sesion_iniciada_codigo_cero(monkeypatch):
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/usr/bin/claude")
    visto = _capturar_run(monkeypatch, _Res(0, stdout='{"loggedIn": true}'))
    assert claude_auth.sesion_iniciada() is True
    assert visto["argv"] == ["/usr/bin/claude", "auth", "status"]


def test_sesion_iniciada_evidencia_positiva_devuelve_false(monkeypatch):
    """Salida ≠ 0 con una pista de PISTAS_LOGIN → sí se puede afirmar que no hay sesión."""
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/usr/bin/claude")
    _capturar_run(monkeypatch, _Res(1, stderr="Not logged in"))
    assert claude_auth.sesion_iniciada() is False


def test_sesion_iniciada_salida_no_reconocida_devuelve_true(monkeypatch):
    """Salida ≠ 0 sin ninguna pista → no se puede determinar, no se bloquea al usuario."""
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/usr/bin/claude")
    _capturar_run(monkeypatch, _Res(1, stderr="algo inesperado"))
    assert claude_auth.sesion_iniciada() is True


def test_sesion_iniciada_cli_antiguo_no_bloquea(monkeypatch):
    """Un CLI anterior a los subcomandos `auth` no imprime ninguna pista de sesión:
    cae en «no se puede determinar», no en «sin sesión»."""
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/usr/bin/claude")
    _capturar_run(monkeypatch, _Res(1, stderr="error: unknown command 'auth'"))
    assert claude_auth.sesion_iniciada() is True


def test_sesion_iniciada_timeout_no_se_puede_determinar(monkeypatch):
    """Un CLI antiguo interpreta «auth status» como prompt y se queda esperando
    entrada hasta agotar el timeout: no se puede determinar, no se bloquea."""
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/usr/bin/claude")
    _capturar_run(monkeypatch, subprocess.TimeoutExpired(cmd="claude", timeout=10))
    assert claude_auth.sesion_iniciada() is True


def test_sesion_iniciada_fallo_al_lanzar_no_se_puede_determinar(monkeypatch):
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/usr/bin/claude")
    _capturar_run(monkeypatch, OSError("no se pudo ejecutar"))
    assert claude_auth.sesion_iniciada() is True


def test_sesion_iniciada_pasa_timeout_y_nunca_shell(monkeypatch):
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: "/usr/bin/claude")
    visto = _capturar_run(monkeypatch, _Res(0))
    claude_auth.sesion_iniciada()
    assert visto["kwargs"]["timeout"] == claude_auth.TIMEOUT_SESION
    assert "shell" not in visto["kwargs"]
    assert visto["kwargs"]["stdin"] == subprocess.DEVNULL


def test_sesion_iniciada_windows_no_abre_ventana_de_consola(monkeypatch):
    monkeypatch.setattr(claude_auth.os, "name", "nt")
    monkeypatch.setattr(claude_auth, "ruta_cli", lambda: r"C:\claude.exe")
    visto = _capturar_run(monkeypatch, _Res(0))
    claude_auth.sesion_iniciada()
    assert "creationflags" in visto["kwargs"]
