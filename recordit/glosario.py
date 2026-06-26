"""Glosario editable para sesgar la transcripción (parámetro `hotwords`).

Combina dos fuentes, en este orden:

  1. El glosario por defecto versionado en el repo: ``recordit/glosario.txt``
     (viaja con la app empaquetada y trae unos términos de ejemplo genéricos).
  2. Un glosario editable por el usuario, fuera del repo y del ejecutable:
     ``~/.config/recordit/glosario.txt`` en Linux/Mac y
     ``%APPDATA%/recordit/glosario.txt`` en Windows (ver ``config``).

Formato de ambos ficheros: un término por línea; líneas vacías o que empiezan
por ``#`` se ignoran. Los términos del usuario se añaden a los del repo, sin
duplicar (comparando sin distinguir mayúsculas/acentos de más).
"""
from pathlib import Path

from recordit import config

_RUTA_REPO = Path(__file__).resolve().parent / "glosario.txt"


def _leer(ruta: Path) -> list:
    """Lee un fichero de glosario y devuelve la lista de términos (sin comentarios)."""
    if not ruta.exists():
        return []
    terminos = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            terminos.append(linea)
    return terminos


def terminos() -> list:
    """Lista combinada (repo + usuario) de términos, en orden y sin duplicados."""
    vistos = set()
    salida = []
    for termino in _leer(_RUTA_REPO) + _leer(config.ruta_glosario_usuario()):
        clave = termino.casefold()
        if clave not in vistos:
            vistos.add(clave)
            salida.append(termino)
    return salida


def hotwords() -> str:
    """Términos unidos en un string para el parámetro `hotwords` de faster-whisper.

    Devuelve ``None`` si el glosario está vacío (faster-whisper lo ignora).
    """
    lista = terminos()
    return ", ".join(lista) if lista else None


def bloque_prompt() -> str:
    """Bloque para inyectar en el prompt del acta con el vocabulario canónico.

    Indica a Claude que normalice a estas formas exactas los términos que
    aparezcan mal escritos en la transcripción, sin introducir ninguno que no
    esté. Devuelve "" si el glosario está vacío.
    """
    lista = terminos()
    if not lista:
        return ""
    return (
        "Vocabulario propio de la organización (nombres de producto, marcas y "
        "términos técnicos). Si en la transcripción aparece alguno de estos "
        "términos mal escrito o con variantes fonéticas, NORMALÍZALO a esta "
        "forma exacta. NO introduzcas ninguno de estos términos si no está "
        "presente en la transcripción:\n"
        + ", ".join(lista)
    )


if __name__ == "__main__":
    import sys

    if "--prompt" in sys.argv:
        print(bloque_prompt())
    else:
        for _termino in terminos():
            print(_termino)
