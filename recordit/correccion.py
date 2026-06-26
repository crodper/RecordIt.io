"""Post-corrección determinista de la transcripción.

Es la red de seguridad del glosario (ver `glosario`): los hotwords sesgan el
reconocimiento, pero cuando aun así Whisper escribe mal un nombre propio, aquí
lo arreglamos sobre el texto ya transcrito. Combina dos mecanismos, ambos
seguros porque solo actúan sobre coincidencias exactas:

  1. **Normalización desde el glosario**: cada término del glosario se fuerza a
     su forma canónica (p. ej. ``modbus`` -> ``Modbus``). Arregla
     mayúsculas/minúsculas sin tener que listarlas a mano.
  2. **Correcciones explícitas**: un mapa ``incorrecto => correcto`` para errores
     fonéticos o de partición de palabras (``zig bee`` -> ``Zigbee``), leído
     de ``recordit/correcciones.txt`` + ``~/.config/recordit/correcciones.txt``.

La búsqueda es insensible a mayúsculas y respeta límites de palabra; el
resultado usa siempre la forma canónica. Las reglas se aplican de más larga a
más corta para que las expresiones de varias palabras ganen a las de una.
"""
import re
from pathlib import Path

from recordit import config, glosario

_RUTA_REPO = Path(__file__).resolve().parent / "correcciones.txt"


def _leer_correcciones(ruta: Path) -> list:
    """Lee un fichero ``incorrecto => correcto`` y devuelve pares (incorrecto, correcto)."""
    if not ruta.exists():
        return []
    pares = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=>" not in linea:
            continue
        incorrecto, correcto = linea.split("=>", 1)
        incorrecto, correcto = incorrecto.strip(), correcto.strip()
        if incorrecto and correcto:
            pares.append((incorrecto, correcto))
    return pares


def _correcciones_pares() -> list:
    """Correcciones explícitas (repo + usuario); el usuario va detrás (manda)."""
    return _leer_correcciones(_RUTA_REPO) + _leer_correcciones(config.ruta_correcciones_usuario())


def _glosario_pares() -> list:
    """Normalización del glosario: cada término es a la vez patrón y forma correcta."""
    return [(t, t) for t in glosario.terminos()]


def _compilar(pares) -> list:
    """Compila pares (patrón, correcto) a (regex, correcto), de más largo a más corto.

    El orden por longitud hace que las expresiones de varias palabras ganen a las
    de una (p. ej. una regla de dos palabras antes que la de una).
    """
    salida = []
    for patron, correcto in sorted(pares, key=lambda p: len(p[0]), reverse=True):
        regex = re.compile(rf"\b{re.escape(patron)}\b", re.IGNORECASE)
        salida.append((regex, correcto))
    return salida


def reglas() -> list:
    """Reglas en el orden de aplicación correcto: correcciones y luego normalización.

    Primero las correcciones explícitas (arreglan el error de transcripción) y
    DESPUÉS la normalización del glosario (arregla la capitalización del
    resultado: 'mod bus' -> 'Modbus').
    """
    return _compilar(_correcciones_pares()) + _compilar(_glosario_pares())


def corregir(texto: str, reglas_compiladas=None) -> str:
    """Aplica las correcciones a `texto`.

    reglas_compiladas: lista de reglas() ya construida (para reutilizarla en
    bucle y no recompilar por cada segmento). Si es None, se construye al vuelo.
    """
    if reglas_compiladas is None:
        reglas_compiladas = reglas()
    for regex, correcto in reglas_compiladas:
        texto = regex.sub(correcto, texto)
    return texto
