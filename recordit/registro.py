"""Registro (logging) y saneado de E/S estándar para la app empaquetada.

En el `.exe` de Windows se construye con `console=False` (sin consola), de modo
que `sys.stdout` y `sys.stderr` son `None`. Cualquier librería que escriba por
ahí (p. ej. `tqdm` o `huggingface_hub` al descargar el modelo) lanzaría
`AttributeError: 'NoneType' object has no attribute 'write'` y la operación
fallaría sin dejar rastro. Aquí dejamos esos flujos apuntando al log y volcamos
los tracebacks a un fichero para poder diagnosticar fallos del binario.
"""
import io
import logging
import sys

from . import rutas


def ruta_log():
    """Ruta del fichero de log (junto a los datos del usuario)."""
    return rutas.base_datos() / "recordit.log"


class _FlujoALog(io.TextIOBase):
    """Flujo de texto que reenvía lo escrito al logging, línea a línea.

    Sustituto de stdout/stderr cuando son None (modo sin consola), para que las
    escrituras de librerías de terceros no revienten y queden en el log.
    """

    def __init__(self, logger):
        self._logger = logger
        self._buffer = ""

    def write(self, s):
        self._buffer += s
        # tqdm usa '\r'; normalizamos para no acumular indefinidamente.
        self._buffer = self._buffer.replace("\r", "\n")
        while "\n" in self._buffer:
            linea, self._buffer = self._buffer.split("\n", 1)
            if linea.strip():
                self._logger.info(linea)
        return len(s)

    def flush(self):
        if self._buffer.strip():
            self._logger.info(self._buffer.strip())
        self._buffer = ""


def configurar():
    """Configura el log a fichero y sanea stdout/stderr nulos. Idempotente."""
    ruta = ruta_log()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(ruta), level=logging.INFO, force=True,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.stdout is None or sys.stderr is None:
        destino = _FlujoALog(logging.getLogger("stdio"))
        if sys.stdout is None:
            sys.stdout = destino
        if sys.stderr is None:
            sys.stderr = destino
    return ruta


def registrar_excepcion(contexto: str):
    """Registra en el log la excepción en curso (con traceback). Devuelve la ruta.

    Debe llamarse dentro de un bloque `except`.
    """
    logging.getLogger("recordit").exception(contexto)
    return ruta_log()
