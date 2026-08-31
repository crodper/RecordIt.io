"""Conexión con Claude para redactar actas, gestionada por recordIt.

El usuario no introduce ninguna API key a mano. recordIt detecta cómo conectar
desde el propio sistema y lo persiste (en config):

1. Claude Code (CLI `claude`) instalado → se usa como backend, sin API key.
2. Variable de entorno ANTHROPIC_API_KEY → se usa la API de Anthropic.
3. Si no hay nada disponible, la GUI instala Claude Code con el instalador
   nativo y abre el inicio de sesión.

Método persistido en config:
  {"metodo": "cli"}                      → usa el CLI `claude`
  {"metodo": "api", "api_key": "sk-..."} → usa la API
"""
import os
import shlex
import shutil
import subprocess
import sys

from . import config

# Guía oficial de instalación (instalador nativo).
URL_AYUDA = "https://code.claude.com/docs/es/setup#native-install-recommended"

# Instalador nativo oficial: no necesita Node.js ni permisos de administrador.
_INSTALADOR_WIN = "irm https://claude.ai/install.ps1 | iex"
_INSTALADOR_POSIX = "curl -fsSL https://claude.ai/install.sh | bash"


def comando_instalacion() -> str:
    """Comando del instalador nativo, tal y como lo escribiría el usuario."""
    return _INSTALADOR_WIN if os.name == "nt" else _INSTALADOR_POSIX


# Margen amplio: la descarga del binario puede tardar en redes lentas.
TIMEOUT_INSTALACION = 300


def _argv_instalacion():
    """Argv del instalador nativo (nunca shell=True: el comando va literal)."""
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command", _INSTALADOR_WIN]
    # -o pipefail: sin él, `curl ... | bash` sale con el código del último
    # comando (bash), así que una descarga fallida con red caída se ve como
    # éxito. Con pipefail, el fallo de curl se propaga.
    return ["bash", "-o", "pipefail", "-c", _INSTALADOR_POSIX]


def _kwargs_sin_consola():
    """kwargs extra para no abrir ventana de consola al lanzar un subproceso.

    Solo aplica en Windows: el `.exe` de recordIt se empaqueta sin consola
    (`console=False`), y lanzar ahí una app de consola abre una ventana
    visible aunque se capture su salida. `CREATE_NO_WINDOW` solo existe en el
    módulo `subprocess` de Windows; `getattr` con valor por defecto evita un
    `AttributeError` al importar o probar este módulo en Linux.
    """
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def instalar():
    """Instala Claude Code con el instalador nativo oficial.

    Devuelve (ok, salida). No lanza excepciones: la llama un hilo de la GUI y
    un fallo tiene que poder mostrarse, no tumbar el hilo. Que `ok` sea True no
    garantiza que el CLI quede utilizable: eso lo decide `conectar()`.
    """
    try:
        res = subprocess.run(_argv_instalacion(), capture_output=True, text=True,
                             timeout=TIMEOUT_INSTALACION, encoding="utf-8",
                             errors="replace", stdin=subprocess.DEVNULL,
                             **_kwargs_sin_consola())
    except subprocess.TimeoutExpired:
        return (False, "El instalador tardó demasiado y se ha cancelado.")
    except OSError as exc:
        return (False, f"No se pudo lanzar el instalador: {exc}")
    salida = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
    return (res.returncode == 0, salida)


# Emuladores de terminal probados en Linux, por orden de preferencia.
TERMINALES = ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm")


def abrir_login() -> bool:
    """Abre una terminal ejecutando `claude auth login` para que el usuario inicie sesión.

    El OAuth del CLI necesita una terminal interactiva (pide confirmación y
    abre el navegador), así que no vale con lanzarlo sin consola. Devuelve
    False si no hay CLI instalado, no se encuentra terminal o falla el
    lanzamiento; en ese caso la GUI muestra el paso manual. En macOS la
    terminal se abre con AppleScript (`osascript` + Terminal.app).
    """
    exe = ruta_cli()
    if not exe:
        return False
    if os.name == "nt":
        argv = ["cmd", "/c", "start", "", "cmd", "/k", exe, "auth", "login"]
    elif sys.platform == "darwin":
        # En macOS no hay emuladores de terminal en el PATH: se le pide a
        # Terminal.app que ejecute el login. `do script` recibe una orden de
        # shell, así que la ruta se entrecomilla con shlex (los Mac tienen
        # carpetas con espacios). El literal AppleScript va entre comillas
        # dobles, escapando las que pueda traer la ruta.
        orden = f"{shlex.quote(exe)} auth login"
        literal = '"' + orden.replace("\\", "\\\\").replace('"', '\\"') + '"'
        argv = ["osascript",
                "-e", f"tell application \"Terminal\" to do script {literal}",
                "-e", 'tell application "Terminal" to activate']
    else:
        terminal = next((t for t in TERMINALES if shutil.which(t)), None)
        if not terminal:
            return False
        # gnome-terminal no acepta argumentos sueltos tras -e; usa «--».
        separador = "--" if terminal == "gnome-terminal" else "-e"
        argv = [terminal, separador, exe, "auth", "login"]
    try:
        subprocess.Popen(argv)
    except OSError:
        return False
    return True


# `claude auth status` responde en décimas de segundo; si tarda más, algo va mal.
TIMEOUT_SESION = 10

# Subcadenas del stderr/stdout que delatan falta de sesión iniciada. Compartida
# con `acta.py`, que traduce el mismo fallo del CLI a un mensaje accionable.
PISTAS_LOGIN = ("login", "log in", "authenticat", "not logged in",
                "unauthorized", "invalid api key")


def sesion_iniciada() -> bool:
    """True si el CLI tiene sesión iniciada (`claude auth status` sale con 0).

    Hay tres desenlaces, no dos:
    - Código de salida 0 → hay sesión: True.
    - Código de salida distinto de 0 con evidencia positiva de falta de sesión
      (alguna de `PISTAS_LOGIN` en la salida) → no hay sesión: False.
    - Cualquier otra cosa (timeout, fallo al lanzar el proceso, o una salida
      distinta de 0 sin esa evidencia — p. ej. un CLI anterior a los
      subcomandos `auth` que interpreta «auth status» como prompt) → no se
      puede determinar, y se devuelve True para no dejar al usuario atrapado
      diciéndole que no tiene sesión cuando quizá sí la tiene. Si de verdad no
      la tiene, el error accionable de `acta.py` lo indicará al generar el acta.
    """
    exe = ruta_cli()
    if not exe:
        return False
    try:
        res = subprocess.run([exe, "auth", "status"], capture_output=True, text=True,
                             timeout=TIMEOUT_SESION, encoding="utf-8", errors="replace",
                             stdin=subprocess.DEVNULL, **_kwargs_sin_consola())
    except (subprocess.TimeoutExpired, OSError):
        return True
    if res.returncode == 0:
        return True
    bajo = ((res.stderr or "") + " " + (res.stdout or "")).lower()
    return not any(pista in bajo for pista in PISTAS_LOGIN)


def ruta_cli():
    """Ruta completa al ejecutable de Claude Code, o None.

    En Windows el CLI es claude.cmd/claude.exe y a veces no está en el PATH del
    proceso de la GUI; por eso, además del PATH, se prueban ubicaciones típicas.
    """
    p = shutil.which("claude")
    if p:
        return p
    home = os.path.expanduser("~")
    if os.name == "nt":
        for ext in (".cmd", ".exe", ".bat", ".ps1"):
            p = shutil.which("claude" + ext)
            if p:
                return p
        candidatos = [
            os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "claude", "claude.exe"),
            os.path.join(home, ".local", "bin", "claude.exe"),
            os.path.join(home, ".local", "bin", "claude.cmd"),
            os.path.join(home, ".claude", "local", "claude.cmd"),
        ]
    else:
        candidatos = [
            os.path.join(home, ".local", "bin", "claude"),
            "/usr/local/bin/claude",
            "/usr/bin/claude",
        ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    return None


def _cli_disponible() -> bool:
    return ruta_cli() is not None


def detectar():
    """Detecta un método de conexión disponible en el sistema (sin persistir).

    Devuelve (metodo, detalle): ('cli', None) | ('api', api_key) | (None, None).
    """
    if _cli_disponible():
        return ("cli", None)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return ("api", key)
    return (None, None)


def estado():
    """Método ya configurado y todavía válido en este sistema.

    Devuelve (metodo, detalle) como `detectar`, pero a partir de lo persistido.
    """
    datos = config.cargar()
    metodo = datos.get("metodo")
    if metodo == "cli" and _cli_disponible():
        return ("cli", None)
    if metodo == "api" and datos.get("api_key"):
        return ("api", datos["api_key"])
    return (None, None)


def conectado() -> bool:
    return estado()[0] is not None


def conectar():
    """Intenta conectar con lo que haya en el sistema y lo persiste.

    Devuelve (metodo, mensaje). metodo es None si no se encontró nada (en cuyo
    caso la GUI debe guiar al usuario a instalar Claude Code).
    """
    metodo, detalle = detectar()
    datos = config.cargar()
    if metodo == "cli":
        datos["metodo"] = "cli"
        datos.pop("api_key", None)
        config.guardar(datos)
        return ("cli", "Conectado mediante Claude Code (CLI) del sistema.")
    if metodo == "api":
        datos["metodo"] = "api"
        datos["api_key"] = detalle
        config.guardar(datos)
        return ("api", "Conectado con la API (variable ANTHROPIC_API_KEY).")
    return (None, "No se encontró Claude en el sistema.")
