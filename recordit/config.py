"""Configuración de usuario: API key de Anthropic y modelo del acta.

Se guarda fuera del repo y del ejecutable, en la carpeta de config del SO.
NUNCA se versiona la API key.
"""
import json
import os
from pathlib import Path

MODELO_POR_DEFECTO = "claude-opus-4-8"
PROVEEDOR_POR_DEFECTO = "claude"
MODELO_OPENAI_POR_DEFECTO = "gpt-5"


def _dir_config() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "recordit"


def ruta_config() -> Path:
    return _dir_config() / "config.json"


def ruta_glosario_usuario() -> Path:
    """Glosario editable por el usuario (override del glosario del repo)."""
    return _dir_config() / "glosario.txt"


def ruta_correcciones_usuario() -> Path:
    """Correcciones editables por el usuario (override de las del repo)."""
    return _dir_config() / "correcciones.txt"


def cargar() -> dict:
    p = ruta_config()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def guardar(datos: dict) -> None:
    p = ruta_config()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def api_key():
    return cargar().get("api_key") or None


def modelo_acta() -> str:
    return cargar().get("modelo_acta", MODELO_POR_DEFECTO)


def proveedor() -> str:
    """Proveedor de IA para redactar el acta: 'claude' (defecto) u 'openai'."""
    return cargar().get("proveedor", PROVEEDOR_POR_DEFECTO)


def openai_api_key():
    return cargar().get("openai_api_key") or None


def modelo_openai() -> str:
    return cargar().get("modelo_openai", MODELO_OPENAI_POR_DEFECTO)


def microfono():
    """Nombre del último micrófono usado (para reseleccionarlo al arrancar)."""
    return cargar().get("microfono") or None


def guardar_microfono(nombre: str) -> None:
    datos = cargar()
    datos["microfono"] = nombre
    guardar(datos)
