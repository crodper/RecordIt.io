"""Resolución de carpetas y nombres de fichero de recordIt.

En modo desarrollo, los datos viven en la raíz del repo (junto a los scripts).
En modo empaquetado (PyInstaller), viven en la carpeta del usuario para no
depender de rutas de solo lectura como Program Files.
La variable de entorno RECORDIT_DATA_DIR fuerza la raíz (útil en tests).
"""
import os
import sys
from pathlib import Path


def _es_empaquetado() -> bool:
    return getattr(sys, "frozen", False)


def base_datos() -> Path:
    """Carpeta raíz donde viven grabaciones/ y transcripciones/."""
    override = os.environ.get("RECORDIT_DATA_DIR")
    if override:
        return Path(override)
    if _es_empaquetado():
        return Path.home() / "recordIt"
    # modo dev: la raíz del repo (este fichero está en recordit/)
    return Path(__file__).resolve().parent.parent


def dir_grabaciones() -> Path:
    d = base_datos() / "grabaciones"
    d.mkdir(parents=True, exist_ok=True)
    return d


def dir_reunion(base: str) -> Path:
    d = base_datos() / "transcripciones" / base
    d.mkdir(parents=True, exist_ok=True)
    return d


def base_desde_audio(audio) -> str:
    """Nombre base (sin extensión) de un fichero de audio."""
    return Path(audio).stem


def ruta_transcripcion(base: str) -> Path:
    return dir_reunion(base) / "transcripcion.txt"


def ruta_timestamps(base: str) -> Path:
    return dir_reunion(base) / "transcripcion_timestamps.txt"


def ruta_acta_md(base: str, fecha_iso: str = None) -> Path:
    """Ruta del acta. Si se da `fecha_iso` (AAAA-MM-DD), va en el nombre."""
    nombre = f"acta_{fecha_iso}.md" if fecha_iso else "acta.md"
    return dir_reunion(base) / nombre


def ruta_clean(base: str) -> Path:
    return dir_reunion(base) / "clean_16k.wav"
