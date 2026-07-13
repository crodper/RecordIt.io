#!/usr/bin/env python3
"""Graba audio del micrófono a un .wav (CLI sobre recordit.audio).

Graba hasta Ctrl+C, escribiendo al disco en tiempo real. La lógica vive en
recordit/audio.py para poder reutilizarla desde la GUI.

Uso:
    python grabar_reunion.py                  # graba a grabaciones/ hasta Ctrl+C
    python grabar_reunion.py --listar         # lista micrófonos
    python grabar_reunion.py -o salida.wav    # nombre de salida concreto
    python grabar_reunion.py --ganancia 3     # ganancia fija (o 'off')
    python grabar_reunion.py --transcribir    # graba y transcribe simultáneamente
"""
import argparse
import sys
import threading

import sounddevice as sd

from recordit import audio, rutas, transcripcion_vivo


def listar_dispositivos() -> None:
    print("Dispositivos de entrada disponibles:\n")
    for indice, info in enumerate(sd.query_devices()):
        if info["max_input_channels"] > 0:
            print(f"  [{indice}] {info['name']} "
                  f"({info['max_input_channels']} canal/es, "
                  f"{int(info['default_samplerate'])} Hz)")


def barra_nivel(pico_dbfs: float, ancho=30) -> str:
    minimo = -60.0
    proporcion = max(0.0, min(1.0, (pico_dbfs - minimo) / (0.0 - minimo)))
    llenos = int(proporcion * ancho)
    return "#" * llenos + "-" * (ancho - llenos)


def parse_ganancia(valor: str):
    if valor is None or valor.lower() == "auto":
        return None
    if valor.lower() in ("off", "no", "0"):
        return 1.0
    return float(valor)


def main() -> None:
    parser = argparse.ArgumentParser(description="Graba audio del micrófono a .wav")
    parser.add_argument("-o", "--salida", help="Fichero .wav de salida")
    parser.add_argument("-r", "--frecuencia", type=int, default=44100)
    parser.add_argument("-c", "--canales", type=int, default=1)
    parser.add_argument("-d", "--duracion", type=float, default=None)
    parser.add_argument("--dispositivo", type=int, default=None)
    parser.add_argument("-g", "--ganancia", default="auto",
                        help="'auto' (AGC), un número (fija) u 'off'")
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--transcribir", action="store_true",
                        help="transcribe en segundo plano mientras graba "
                             "(la transcripción queda lista al parar)")
    args = parser.parse_args()

    if args.listar:
        listar_dispositivos()
        return

    salida = args.salida or str(rutas.dir_grabaciones() / audio.nombre_archivo())
    evento = threading.Event()

    vivo = None
    if args.transcribir:
        if args.canales != 1:
            print("Aviso: la transcripción en vivo requiere audio mono; se graba sin ella.")
        else:
            frecuencia = audio.frecuencia_soportada(
                args.dispositivo, args.frecuencia, args.canales)
            base = rutas.base_desde_audio(salida)
            vivo = transcripcion_vivo.crear(base, frecuencia)
            if vivo is None:
                print("Aviso: el modelo large-v3 no está descargado; "
                      "se graba sin transcripción en vivo.")

    def nivel(pico_db, ganancia_db):
        aviso = " SATURA!" if pico_db > -3.0 else (" (muy bajo)" if pico_db < -45.0 else "")
        print(f"\r[{barra_nivel(pico_db)}] {pico_db:5.0f} dB  "
              f"gan +{ganancia_db:4.1f} dB{aviso}      ", end="", flush=True)

    print(f"Grabando en «{salida}». Pulsa Ctrl+C para parar y guardar.\n")
    try:
        segundos = audio.grabar(
            salida, evento_parada=evento, nivel_callback=nivel,
            frecuencia=args.frecuencia, canales=args.canales,
            dispositivo=args.dispositivo, duracion_max=args.duracion,
            ganancia=parse_ganancia(args.ganancia),
            muestras_callback=vivo.alimentar if vivo else None,
        )
    except KeyboardInterrupt:
        evento.set()
        segundos = 0.0
    print(f"\n\nGuardado: {salida}")
    if vivo is not None:
        print("Terminando la transcripción de los últimos minutos…")
        if vivo.finalizar():
            print(f"Transcripción lista: {rutas.ruta_transcripcion(base)}")
        else:
            print("La transcripción en vivo falló; ejecuta transcribir.py sobre el .wav.")


if __name__ == "__main__":
    main()
