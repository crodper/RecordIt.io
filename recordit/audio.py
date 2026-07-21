"""Grabación de audio del micrófono, controlable por código.

A diferencia del script original (que paraba con Ctrl+C), `grabar()` se detiene
cuando se activa un threading.Event, de modo que la GUI pueda pararla con un
botón. Mantiene el AGC, el VU meter (vía callback) y la escritura incremental.
"""
import contextlib
import datetime as dt
import math
import os
import queue
import wave

import numpy as np
import sounddevice as sd

from recordit import registro

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


def remuestrear(muestras, frecuencia_origen, frecuencia_destino):
    """Remuestrea un array int16 mono a otra frecuencia por interpolación lineal.

    Sin dependencias extra (solo numpy). Calidad de sobra para transcribir voz.
    Si las frecuencias coinciden devuelve las muestras tal cual.
    """
    if frecuencia_origen == frecuencia_destino or muestras.size == 0:
        return muestras
    n_destino = int(round(muestras.size * frecuencia_destino / frecuencia_origen))
    if n_destino <= 0:
        return np.zeros(0, dtype=np.int16)
    x_orig = np.arange(muestras.size, dtype=np.float64)
    x_dest = np.linspace(0, muestras.size - 1, n_destino)
    interp = np.interp(x_dest, x_orig, muestras.astype(np.float64))
    return np.clip(np.round(interp), -32768, 32767).astype(np.int16)


def mezclar(bloque_mic, bloque_salida):
    """Suma micro + salida en un mono int16, recortando al rango válido.

    Alinea a la longitud del bloque de micro: rellena la salida con ceros si
    va corta y la trunca si va larga (así la escritura del .wav marca el ritmo).
    Sumar (no promediar) mantiene ambas voces a volumen pleno; el clip protege
    el pico raro en que los dos hablan fuerte a la vez.
    """
    n = bloque_mic.size
    salida = bloque_salida[:n]
    if salida.size < n:
        salida = np.concatenate([salida, np.zeros(n - salida.size, dtype=np.int16)])
    suma = bloque_mic.astype(np.int32) + salida.astype(np.int32)
    return np.clip(suma, -32768, 32767).astype(np.int16)


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


def seleccionar_salidas(dispositivos, hostapis, nombre_sink_defecto=None):
    """Fuentes capturables de la salida del sistema, ordenadas (defecto primero).

    Función pura (no toca sounddevice) para poder probarla. Devuelve tuplas
    (indice, etiqueta, nombre, loopback):
    - `loopback=True`  -> abrir el dispositivo de SALIDA en modo WASAPI loopback
      (Windows).
    - `loopback=False` -> abrir una fuente `*.monitor` como ENTRADA normal
      (PulseAudio/PipeWire en Linux).

    En Windows se usan los dispositivos de salida del API WASAPI. En Linux se
    usan las fuentes `*.monitor` de PulseAudio. En ALSA puro (sin PulseAudio ni
    WASAPI) no hay loopback fiable y se devuelve lista vacía.
    """
    nombre_api = {i: h["name"] for i, h in enumerate(hostapis)}
    api_wasapi = next((i for i, n in nombre_api.items() if "WASAPI" in n), None)
    hay_pulse = "PulseAudio" in nombre_api.values()

    salidas = []
    if api_wasapi is not None:
        for indice, info in enumerate(dispositivos):
            if info["hostapi"] == api_wasapi and info["max_output_channels"] > 0:
                nombre = info["name"].strip()
                salidas.append((indice, f"{nombre}  ·  audio del sistema",
                                nombre, True))
        clave_defecto = nombre_sink_defecto
    elif hay_pulse:
        api_pulse = next(i for i, n in nombre_api.items() if n == "PulseAudio")
        for indice, info in enumerate(dispositivos):
            nombre = info["name"].strip()
            if (info["hostapi"] == api_pulse
                    and info["max_input_channels"] > 0
                    and nombre.endswith(".monitor")):
                salidas.append((indice, f"{nombre}  ·  audio del sistema",
                                nombre, False))
        clave_defecto = f"{nombre_sink_defecto}.monitor" if nombre_sink_defecto else None
    else:
        return []

    salidas.sort(key=lambda s: 0 if s[2] == clave_defecto else 1)
    return salidas


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


def listar_salidas(reescanear=False):
    """Salidas del sistema capturables (monitor/loopback), etiquetadas.

    Mismo patrón que `listar_microfonos`: si `reescanear` es True reinicia
    PortAudio para redetectar hardware. No usar `reescanear=True` con una
    grabación en curso.
    """
    if reescanear:
        sd._terminate()
        sd._initialize()
    try:
        indice_sink = sd.default.device[1]
        nombre_sink = sd.query_devices(indice_sink)["name"].strip()
    except Exception:  # noqa: BLE001
        nombre_sink = None
    return seleccionar_salidas(sd.query_devices(), sd.query_hostapis(), nombre_sink)


def salida_sistema_por_defecto():
    """(indice, loopback) de la mejor salida capturable, o None si no hay.

    Lo usa el modo «reunión online» para auto-detectar la salida sin pedir al
    usuario que elija dispositivo.
    """
    salidas = listar_salidas()
    if not salidas:
        return None
    indice, _etq, _nom, loopback = salidas[0]
    return indice, loopback


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
           duracion_max=None, ganancia=None, muestras_callback=None,
           fuente_salida=None, salida_loopback=False) -> float:
    """Graba del micrófono a un .wav hasta que se active `evento_parada`.

    ganancia: None -> AGC automático; float -> ganancia fija (1.0 = sin cambio).
    nivel_callback(pico_db, ganancia_db): se llama por bloque (para el VU meter).
    muestras_callback(bytes): recibe cada bloque int16 recién escrito (transcripción en vivo).
    fuente_salida: índice del dispositivo de salida del sistema a capturar y
        mezclar con el micro (modo reunión online). None -> solo micro.
    salida_loopback: True en Windows (abrir la salida en modo WASAPI loopback);
        False en Linux (fuente monitor como entrada normal).
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

    # --- captura opcional de la salida del sistema (reunión online) ---------
    cola_salida: "queue.Queue" = queue.Queue()
    stream_salida = None
    buffer_salida = np.zeros(0, dtype=np.int16)
    tope_buffer = int(2 * frecuencia)  # ~2 s: acota la deriva entre relojes

    if fuente_salida is not None:
        try:
            info_sal = sd.query_devices(fuente_salida)
            clave_principal = "max_output_channels" if salida_loopback else "max_input_channels"
            clave_secundaria = "max_input_channels" if salida_loopback else "max_output_channels"
            canales_sal = max(1, int(info_sal.get(clave_principal)
                                     or info_sal.get(clave_secundaria) or 1))
            frecuencia_sal = frecuencia_soportada(fuente_salida, frecuencia, canales_sal)

            def callback_salida(datos, frames, tiempo, estado):
                bloque = datos.astype(np.float32)
                mono = bloque.mean(axis=1) if bloque.ndim > 1 else bloque
                mono16 = mono.astype(np.int16)
                remuestreado = remuestrear(mono16, frecuencia_sal, frecuencia)
                cola_salida.put(remuestreado.tobytes())

            extra = None
            if salida_loopback and hasattr(sd, "WasapiSettings"):
                extra = sd.WasapiSettings(loopback=True)
            stream_salida = sd.InputStream(
                samplerate=frecuencia_sal, blocksize=BLOQUE, channels=canales_sal,
                dtype="int16", device=fuente_salida, callback=callback_salida,
                extra_settings=extra,
            )
        except Exception:  # noqa: BLE001 — sin loopback se graba solo micro
            registro.registrar_excepcion("captura de la salida del sistema")
            stream_salida = None

    segundos_escritos = 0.0
    inicio = dt.datetime.now()
    try:
        with contextlib.ExitStack() as pila:
            pila.enter_context(stream)
            if stream_salida is not None:
                try:
                    pila.enter_context(stream_salida)
                except Exception:  # noqa: BLE001 — si no arranca, grabamos solo micro
                    registro.registrar_excepcion("captura de la salida del sistema (inicio)")
                    try:
                        stream_salida.close()
                    except Exception:  # noqa: BLE001 — cerrar tampoco debe tumbar
                        pass
                    stream_salida = None
            while not evento_parada.is_set():
                if stream_salida is not None:
                    # Drenar la salida SIEMPRE, aunque el micro se atasque, para
                    # que cola_salida no crezca sin límite; buffer_salida queda
                    # acotado a ~2 s.
                    while True:
                        try:
                            buffer_salida = np.concatenate(
                                [buffer_salida,
                                 np.frombuffer(cola_salida.get_nowait(), dtype=np.int16)])
                        except queue.Empty:
                            break
                    if buffer_salida.size > tope_buffer:  # acota la deriva
                        buffer_salida = buffer_salida[-tope_buffer:]
                try:
                    bytes_audio, pico_db, ganancia_db = cola.get(timeout=0.1)
                except queue.Empty:
                    continue
                if stream_salida is not None:
                    mic = np.frombuffer(bytes_audio, dtype=np.int16)
                    n = mic.size
                    mezcla = mezclar(mic, buffer_salida[:n])
                    buffer_salida = buffer_salida[n:]
                    bytes_audio = mezcla.tobytes()
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
