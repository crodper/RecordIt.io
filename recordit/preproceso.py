"""Preprocesado de audio con ffmpeg: denoise + normalize + 16 kHz mono.

Es lo que mejora la calidad de la transcripción en audio de sala. Localiza el
binario de ffmpeg empaquetado junto al ejecutable y, si no, el del PATH.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

FILTRO_AUDIO = "highpass=f=80,lowpass=f=8000,afftdn=nf=-25,dynaudnorm=f=150:g=15"


def ruta_ffmpeg() -> str:
    """Devuelve la ruta a ffmpeg: empaquetado primero, si no el del PATH."""
    if getattr(sys, "frozen", False):
        nombre = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        # En one-file, los binarios empaquetados se extraen en sys._MEIPASS,
        # no junto al ejecutable; probamos ahí primero.
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        candidato = Path(base) / nombre
        if candidato.exists():
            return str(candidato)
    encontrado = shutil.which("ffmpeg")
    if not encontrado:
        raise FileNotFoundError("No se encontró ffmpeg (ni empaquetado ni en el PATH).")
    return encontrado


def construir_orden(entrada, salida, ffmpeg=None) -> list:
    """Construye la orden de ffmpeg para limpiar y bajar a 16 kHz mono."""
    ffmpeg = ffmpeg or ruta_ffmpeg()
    return [
        ffmpeg, "-y", "-loglevel", "error", "-i", str(entrada),
        "-af", FILTRO_AUDIO,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(salida),
    ]


def preprocesar(entrada, salida, ffmpeg=None) -> None:
    """Ejecuta ffmpeg sobre `entrada` y escribe `salida` (16 kHz mono)."""
    subprocess.run(construir_orden(entrada, salida, ffmpeg), check=True)
