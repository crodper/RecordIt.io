"""Detección de una versión más reciente publicada en GitHub.

Consulta la API de releases de GitHub (anónima) y la compara con la versión
actual. Diseño defensivo: cualquier fallo (sin red, timeout, HTTP, JSON
inesperado, tag no parseable) devuelve None. Nunca lanza; el arranque no debe
romperse por comprobar actualizaciones. Solo urllib (sin dependencias nuevas).
"""
import json
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com/repos/crodper/RecordIt.io/releases/latest"
TIMEOUT = 8


def _a_tupla(version):
    """'v0.6.0'/'0.6.0' -> (0, 6, 0); None si algún componente no es entero."""
    try:
        limpia = version.strip().lstrip("vV")
        return tuple(int(p) for p in limpia.split("."))
    except (ValueError, AttributeError):
        return None


def _es_mas_nueva(remota, actual) -> bool:
    tr, ta = _a_tupla(remota), _a_tupla(actual)
    if tr is None or ta is None:
        return False
    return tr > ta


def _pedir(url: str, cabeceras: dict) -> dict:
    req = urllib.request.Request(url, headers=cabeceras)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def comprobar_actualizacion(version_actual, origen=None, token=None):
    """Devuelve {"version","url","notas"} si hay una release más nueva, o None.

    `origen`/`token` se aceptan por compatibilidad de firma con la GUI, pero este
    build solo consulta GitHub. Silencioso ante cualquier error.
    """
    try:
        datos = _pedir(GITHUB_API, {
            "User-Agent": "recordIt-updater",
            "Accept": "application/vnd.github+json"})
        tag = datos.get("tag_name")
        url = datos.get("html_url")
        notas = datos.get("body") or ""
    except (urllib.error.URLError, TimeoutError, ValueError, OSError,
            AttributeError, TypeError):
        return None

    if not tag or not _es_mas_nueva(tag, version_actual):
        return None
    return {"version": tag.strip().lstrip("vV"), "url": url, "notas": notas}
