"""Grabación de audio del micrófono, controlable por código.

A diferencia del script original (que paraba con Ctrl+C), `grabar()` se detiene
cuando se activa un threading.Event, de modo que la GUI pueda pararla con un
botón. Mantiene el AGC, el VU meter (vía callback) y la escritura incremental.
"""
import datetime as dt
import math
import os
import queue
import wave

import numpy as np
import sounddevice as sd

BLOQUE = 1024            # frames por bloque (~23 ms a 44100 Hz)
OBJETIVO_DBFS = -20.0    # nivel medio al que apunta la ganancia automática
GANANCIA_MAX_DB = 30.0   # tope de amplificación del AGC
PUERTA_RUIDO_DBFS = -55.0  # por debajo de esto se considera silencio


def nombre_archivo() -> str:
    """Nombre de fichero (sin carpeta) con fecha y hora actuales."""
    marca = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"reunion_{marca}.wav"


def dbfs(valor_lineal: float) -> float:
    """Convierte un valor 0..1 a dBFS (decibelios respecto al máximo)."""
    if valor_lineal <= 1e-9:
        return -120.0
    return 20.0 * math.log10(valor_lineal)


class GananciaAutomatica:
    """AGC sencillo: ajusta la ganancia bloque a bloque hacia un nivel objetivo."""

    def __init__(self, objetivo_dbfs=OBJETIVO_DBFS, max_db=GANANCIA_MAX_DB):
        self.objetivo = objetivo_dbfs
        self.max_db = max_db
        self.ganancia_db = 0.0

    def procesar(self, muestras: np.ndarray) -> np.ndarray:
        """Aplica ganancia adaptativa a un bloque float32 en rango [-1, 1]."""
        rms = float(np.sqrt(np.mean(np.square(muestras)))) if muestras.size else 0.0
        rms_db = dbfs(rms)
        if rms_db > PUERTA_RUIDO_DBFS:  # solo adaptamos cuando hay señal real
            deseada = self.objetivo - rms_db
            deseada = max(0.0, min(self.max_db, deseada))
            paso = 0.15 if deseada > self.ganancia_db else 0.6
            self.ganancia_db += (deseada - self.ganancia_db) * paso
        factor = 10.0 ** (self.ganancia_db / 20.0)
        return np.clip(muestras * factor, -1.0, 1.0)


def _etiqueta_amigable(nombre: str) -> str:
    """Nombre legible para el desplegable a partir del nombre de PortAudio."""
    bajo = nombre.lower()
    if nombre == "Default Source":
        return "Predeterminado del sistema"
    if "bluez" in bajo:
        return "Micrófono Bluetooth"
    if "mic" in bajo and "source" in bajo:
        return "Micrófono integrado"
    return nombre


def seleccionar_microfonos(dispositivos, hostapis, predeterminado):
    """Filtra y etiqueta los micrófonos reales a partir de la lista de PortAudio.

    Función pura (sin tocar sounddevice) para poder probarla. Devuelve una lista
    de tuplas (indice, etiqueta, nombre):
    - `indice`: índice de PortAudio (para grabar).
    - `etiqueta`: texto legible para el desplegable.
    - `nombre`: nombre crudo de PortAudio (estable, para persistir la selección).

    En sistemas con PulseAudio/PipeWire, PortAudio expone el mismo grafo por
    varios sitios (ALSA `hw:`, `pipewire`, `default` y, además, el API
    PulseAudio). Para no confundir al usuario con duplicados, si existe el API
    PulseAudio se listan SOLO sus fuentes reales (con nombres amigables) y se
    colapsa el predeterminado en una sola entrada. En sistemas ALSA puros se
    mantiene el listado ALSA (sin monitores).
    """
    nombre_api = {i: h["name"] for i, h in enumerate(hostapis)}
    hay_pulse = "PulseAudio" in nombre_api.values()

    def es_micro(info):
        return info["max_input_channels"] > 0 and "monitor" not in info["name"].lower()

    micros = []
    for indice, info in enumerate(dispositivos):
        if not es_micro(info):
            continue
        api = nombre_api.get(info["hostapi"], "?")
        nombre = info["name"].strip()
        if hay_pulse:
            # Solo las fuentes del API PulseAudio (mapean a nodos reales);
            # esto descarta los duplicados crudos `hw:`, `pipewire`, `default`.
            if api != "PulseAudio":
                continue
            etiqueta = _etiqueta_amigable(nombre)
            if nombre == "Default Source":
                etiqueta += "   (predeterminado)"
        else:
            etiqueta = f"{nombre}  ·  {api}  ·  {info['max_input_channels']} canal/es"
            if indice == predeterminado:
                etiqueta += "   (predeterminado)"
        micros.append((indice, etiqueta, nombre))

    # El predeterminado del sistema primero, para que sea la opción por defecto.
    micros.sort(key=lambda m: 0 if "predeterminado" in m[1].lower() else 1)
    return micros


def listar_microfonos(reescanear=False):
    """Micrófonos disponibles, ya filtrados y etiquetados.

    Si `reescanear` es True, reinicia PortAudio para volver a enumerar el
    hardware (necesario para detectar micros conectados en caliente, p. ej. unos
    auriculares Bluetooth, o un servidor de audio que aún no estaba listo al
    arrancar). NO usar `reescanear=True` con una grabación en curso: rompería el
    stream activo.
    """
    if reescanear:
        sd._terminate()
        sd._initialize()
    try:
        predeterminado = sd.default.device[0]
    except Exception:  # noqa: BLE001
        predeterminado = -1
    return seleccionar_microfonos(sd.query_devices(), sd.query_hostapis(), predeterminado)


def frecuencia_soportada(dispositivo, frecuencia, canales) -> int:
    """Frecuencia válida para el dispositivo.

    Si la pedida no la soporta (típico error PortAudio 'Invalid sample rate'
    con micros que solo aceptan p. ej. 16 kHz o 48 kHz), usa la frecuencia por
    defecto del dispositivo. Así no revienta al abrir el stream.
    """
    try:
        sd.check_input_settings(device=dispositivo, samplerate=frecuencia,
                                channels=canales, dtype="int16")
        return int(frecuencia)
    except Exception:  # noqa: BLE001 — cualquier rechazo de PortAudio
        try:
            info = sd.query_devices(dispositivo, "input")
            return int(info["default_samplerate"])
        except Exception:  # noqa: BLE001
            return int(frecuencia)


def grabar(salida, *, evento_parada, nivel_callback=None,
           frecuencia=44100, canales=1, dispositivo=None,
           duracion_max=None, ganancia=None, muestras_callback=None) -> float:
    """Graba del micrófono a un .wav hasta que se active `evento_parada`.

    ganancia: None -> AGC automático; float -> ganancia fija (1.0 = sin cambio).
    nivel_callback(pico_db, ganancia_db): se llama por bloque (para el VU meter).
    muestras_callback(bytes): recibe cada bloque int16 recién escrito (transcripción en vivo).
    Devuelve los segundos de audio escritos.
    """
    frecuencia = frecuencia_soportada(dispositivo, frecuencia, canales)
    cola: "queue.Queue" = queue.Queue()
    agc = GananciaAutomatica() if ganancia is None else None
    factor_fijo = None if ganancia is None else float(ganancia)

    def callback(datos, frames, tiempo, estado):
        muestras = datos.astype(np.float32) / 32768.0
        if agc is not None:
            muestras = agc.procesar(muestras)
        elif factor_fijo is not None and factor_fijo != 1.0:
            muestras = np.clip(muestras * factor_fijo, -1.0, 1.0)
        pico = float(np.max(np.abs(muestras))) if muestras.size else 0.0
        enteros = (muestras * 32767.0).astype(np.int16)
        ganancia_db = agc.ganancia_db if agc is not None else dbfs(factor_fijo or 1.0)
        cola.put((enteros.tobytes(), dbfs(pico), ganancia_db))

    directorio = os.path.dirname(salida)
    if directorio:
        os.makedirs(directorio, exist_ok=True)

    wav = wave.open(str(salida), "wb")
    wav.setnchannels(canales)
    wav.setsampwidth(2)
    wav.setframerate(frecuencia)

    stream = sd.InputStream(
        samplerate=frecuencia, blocksize=BLOQUE, channels=canales,
        dtype="int16", device=dispositivo, callback=callback,
    )

    segundos_escritos = 0.0
    inicio = dt.datetime.now()
    try:
        with stream:
            while not evento_parada.is_set():
                try:
                    bytes_audio, pico_db, ganancia_db = cola.get(timeout=0.1)
                except queue.Empty:
                    continue
                wav.writeframes(bytes_audio)
                if muestras_callback is not None:
                    muestras_callback(bytes_audio)
                segundos_escritos += len(bytes_audio) / (2 * canales) / frecuencia
                if nivel_callback is not None:
                    nivel_callback(pico_db, ganancia_db)
                transcurrido = (dt.datetime.now() - inicio).total_seconds()
                if duracion_max is not None and transcurrido >= duracion_max:
                    break
    except KeyboardInterrupt:
        pass  # la CLI usa Ctrl+C como parada
    finally:
        wav.close()
    return segundos_escritos
