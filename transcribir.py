#!/usr/bin/env python3
"""Transcribe un .wav con faster-whisper (CLI sobre recordit.transcripcion).

Uso:
    python transcribir.py <audio.wav> <salida.txt>
El fichero con timestamps se escribe junto al de texto plano.
"""
import datetime as dt
import sys
from pathlib import Path

from recordit import glosario, transcripcion


def main() -> None:
    audio = sys.argv[1] if len(sys.argv) > 1 else "reunion_clean_16k.wav"
    salida_txt = Path(sys.argv[2] if len(sys.argv) > 2 else "transcripciones/transcripcion.txt")
    salida_ts = salida_txt.with_name(salida_txt.stem + "_timestamps.txt")

    if not transcripcion.modelo_en_cache("large-v3"):
        print(f"[{dt.datetime.now():%H:%M:%S}] Descargando modelo large-v3 (puede tardar)...", flush=True)

    def progreso(actual, total):
        print(f"\r[{dt.datetime.now():%H:%M:%S}] {actual/60:.1f}/{total/60:.1f} min", end="", flush=True)

    n_glosario = len(glosario.terminos())
    if n_glosario:
        print(f"[{dt.datetime.now():%H:%M:%S}] Glosario: {n_glosario} términos para hotwords", flush=True)

    print(f"[{dt.datetime.now():%H:%M:%S}] Transcribiendo {audio}...", flush=True)
    duracion = transcripcion.transcribir(audio, salida_txt, salida_ts, progreso_callback=progreso)
    print(f"\n[{dt.datetime.now():%H:%M:%S}] Listo ({duracion/60:.1f} min). Guardado en {salida_txt}", flush=True)


if __name__ == "__main__":
    main()
