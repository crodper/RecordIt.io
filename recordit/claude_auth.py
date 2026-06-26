"""Conexión con Claude para redactar actas, gestionada por recordIt.

El usuario no introduce ninguna API key a mano. recordIt detecta cómo conectar
desde el propio sistema y lo persiste (en config):

1. Claude Code (CLI `claude`) instalado → se usa como backend, sin API key.
2. Variable de entorno ANTHROPIC_API_KEY → se usa la API de Anthropic.
3. Si no hay nada disponible, la GUI guía al usuario a instalar Claude Code.

Método persistido en config:
  {"metodo": "cli"}                      → usa el CLI `claude`
  {"metodo": "api", "api_key": "sk-..."} → usa la API
"""
import os
import shutil

from . import config

# Página a la que guiar al usuario si no hay forma de conectar.
URL_AYUDA = "https://claude.com/claude-code"

# Comando para instalar el CLI oficial de Claude Code (requiere Node.js).
COMANDO_INSTALACION = "npm install -g @anthropic-ai/claude-code"


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
