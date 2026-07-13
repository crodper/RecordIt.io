"""Transcripción en vivo mientras se graba.

Consume los bloques int16 que el grabador escribe a disco (vía
``muestras_callback`` de ``audio.grabar``), corta tramos de 60–120 s por el
punto más silencioso, los preprocesa con ffmpeg y los transcribe con los
mismos parámetros que la transcripción clásica. Si algo falla, se apaga solo
y JAMÁS afecta a la grabación: el .wav completo sigue en disco para la
transcripción clásica.
"""
import os
import queue
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

from recordit import correccion, glosario, preproceso, registro, rutas, transcripcion

MIN_TRAMO_S = 60.0    # no cortar antes de este punto
MAX_TRAMO_S = 120.0   # corte forzoso al llegar aquí
VENTANA_MS = 500      # tamaño de la ventana de silencio buscada


def punto_de_corte(muestras, frecuencia, min_s=MIN_TRAMO_S, max_s=MAX_TRAMO_S,
                   ventana_ms=VENTANA_MS):
    """Índice de muestra donde cortar el tramo, o None si aún no toca.

    Busca la ventana de ``ventana_ms`` con menos energía (RMS) entre
    ``min_s`` y ``max_s`` y devuelve su centro: así nunca se corta una
    palabra por la mitad. Devuelve None mientras no haya ``max_s`` segundos
    acumulados.
    """
    if len(muestras) < int(max_s * frecuencia):
        return None
    v = max(1, int(ventana_ms * frecuencia / 1000))
    ini, fin = int(min_s * frecuencia), int(max_s * frecuencia)
    x = muestras[ini:fin].astype(np.float64) ** 2
    acumulada = np.cumsum(x)
    energia = acumulada[v:] - acumulada[:-v]  # energía por ventana deslizante
    return ini + int(np.argmin(energia)) + v // 2


class TranscriptorEnVivo:
    """Transcribe en un hilo de fondo los bloques que le pasa el grabador.

    Uso: crear -> alimentar(bloque) por cada bloque grabado -> finalizar().
    Tras finalizar() con True, transcripcion.txt y _timestamps.txt están
    completos. Ante cualquier error el transcriptor se marca fallido, deja
    de consumir y finalizar() devuelve False (el llamador recurre a la
    transcripción clásica sobre el .wav, que sigue intacto).
    """

    def __init__(self, base, frecuencia, *, min_tramo_s=MIN_TRAMO_S,
                 max_tramo_s=MAX_TRAMO_S, preprocesar=None,
                 cargar_modelo=None, hotwords=None):
        self.base = base
        self.frecuencia = int(frecuencia)
        self.min_tramo_s = min_tramo_s
        self.max_tramo_s = max_tramo_s
        self.duracion = 0.0
        self._preprocesar = preprocesar or preproceso.preprocesar
        self._cargar_modelo = cargar_modelo or transcripcion.cargar_modelo
        self._hotwords = glosario.hotwords() if hotwords is None else hotwords
        self._reglas = correccion.reglas()
        self._cola = queue.Queue()
        self._pendiente = []          # bloques bytes aún sin trocear
        self._muestras_pendientes = 0
        self._modelo = None
        self._f_txt = None
        self._f_ts = None
        self._error = False
        self._parada = threading.Event()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()

    # --- interfaz para el grabador (no bloquea nunca) --------------------
    def alimentar(self, bytes_bloque):
        if not self._error:
            self._cola.put(bytes_bloque)

    def finalizar(self) -> bool:
        """Procesa lo pendiente (incluido el tramo final) y espera al hilo."""
        self._parada.set()
        self._hilo.join()
        return not self._error

    # --- hilo trabajador --------------------------------------------------
    def _trabajar(self):
        try:
            while True:
                self._drenar_cola()
                muestras = self._buffer_np()
                corte = punto_de_corte(muestras, self.frecuencia,
                                       self.min_tramo_s, self.max_tramo_s)
                if corte is not None:
                    self._reponer_buffer(muestras[corte:])
                    self._procesar_tramo(muestras[:corte])
                    continue
                if self._parada.is_set() and self._cola.empty():
                    if len(muestras):
                        self._reponer_buffer(muestras[:0])
                        self._procesar_tramo(muestras)
                    break
        except Exception:  # noqa: BLE001 — la grabación no debe verse afectada
            registro.registrar_excepcion("transcripción en vivo")
            self._error = True
        finally:
            for f in (self._f_txt, self._f_ts):
                if f is not None:
                    f.close()

    def _drenar_cola(self):
        try:
            bloque = self._cola.get(timeout=0.2)
        except queue.Empty:
            return
        while True:
            self._pendiente.append(bloque)
            self._muestras_pendientes += len(bloque) // 2
            try:
                bloque = self._cola.get_nowait()
            except queue.Empty:
                return

    def _buffer_np(self):
        return np.frombuffer(b"".join(self._pendiente), dtype=np.int16)

    def _reponer_buffer(self, resto):
        self._pendiente = [resto.tobytes()] if len(resto) else []
        self._muestras_pendientes = len(resto)

    def _procesar_tramo(self, muestras):
        with tempfile.TemporaryDirectory(prefix="recordit_vivo_") as tmp:
            crudo = Path(tmp) / "tramo.wav"
            limpio = Path(tmp) / "tramo_limpio.wav"
            with wave.open(str(crudo), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.frecuencia)
                w.writeframes(muestras.tobytes())
            self._preprocesar(crudo, limpio)
            if self._modelo is None:
                self._modelo = self._cargar_modelo()
            segments, _info = transcripcion.iterar_segmentos(
                limpio, self._modelo, self._hotwords)
            self._abrir_salidas()
            for seg in segments:
                texto = correccion.corregir(seg.text.strip(), self._reglas)
                ini = transcripcion.hms(seg.start + self.duracion)
                fin = transcripcion.hms(seg.end + self.duracion)
                self._f_ts.write(f"[{ini} -> {fin}] {texto}\n")
                self._f_txt.write(texto + "\n")
                self._f_txt.flush()
                self._f_ts.flush()
        self.duracion += len(muestras) / self.frecuencia

    def _abrir_salidas(self):
        if self._f_txt is None:
            salida_txt = rutas.ruta_transcripcion(self.base)
            salida_txt.parent.mkdir(parents=True, exist_ok=True)
            self._f_txt = open(salida_txt, "w", encoding="utf-8")
            self._f_ts = open(rutas.ruta_timestamps(self.base), "w", encoding="utf-8")


def crear(base, frecuencia):
    """TranscriptorEnVivo listo, o None si no puede haber transcripción en vivo.

    Solo se activa con el modelo ya descargado: la primera ejecución no debe
    ponerse a bajar ~3 GB en mitad de una reunión.
    """
    if not transcripcion.modelo_en_cache():
        return None
    try:
        return TranscriptorEnVivo(base, frecuencia)
    except Exception:  # noqa: BLE001
        registro.registrar_excepcion("crear transcriptor en vivo")
        return None
