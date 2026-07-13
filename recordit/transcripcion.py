"""Transcripción de audio con faster-whisper (large-v3) en CPU.

Mantiene las decisiones que evitan bucles de alucinación con audio de sala:
vad_filter, condition_on_previous_text=False e idioma fijado a 'es'.
"""
import os
from pathlib import Path

from recordit import correccion, glosario


def hms(s) -> str:
    return f"{int(s)//3600:02d}:{int(s)%3600//60:02d}:{int(s)%60:02d}"


def modelo_en_cache(modelo: str = "large-v3") -> bool:
    """¿Está el modelo ya descargado en la caché de Hugging Face?"""
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return (cache / f"models--Systran--faster-whisper-{modelo}").exists()


def cargar_modelo(modelo: str = "large-v3"):
    """Instancia el WhisperModel (descarga el modelo si no está en caché)."""
    from faster_whisper import WhisperModel
    return WhisperModel(modelo, device="cpu", compute_type="int8", cpu_threads=8)


def iterar_segmentos(audio, modelo_obj, hotwords):
    """Única fuente de los parámetros de Whisper (anti-alucinación incluida).

    La usan la transcripción clásica y la transcripción en vivo; cualquier
    ajuste de parámetros debe hacerse SOLO aquí.
    """
    return modelo_obj.transcribe(
        str(audio), language="es", beam_size=5,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=False,
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        hotwords=hotwords or None,
    )


def transcribir(audio, salida_txt, salida_ts, *, modelo="large-v3",
                progreso_callback=None, modelo_cargado=None, hotwords=None) -> float:
    """Transcribe `audio` y escribe texto plano y versión con timestamps.

    progreso_callback(segundos_procesados, duracion_total): para barra de progreso.
    modelo_cargado: WhisperModel ya instanciado (para inyectar en tests).
    hotwords: glosario para sesgar el reconocimiento. Si es None, se usa el
        glosario combinado (repo + usuario); pasar "" lo desactiva.
    Devuelve la duración detectada en segundos.
    """
    if hotwords is None:
        hotwords = glosario.hotwords()
    modelo_obj = modelo_cargado or cargar_modelo(modelo)
    segments, info = iterar_segmentos(audio, modelo_obj, hotwords)
    reglas_correccion = correccion.reglas()
    Path(salida_txt).parent.mkdir(parents=True, exist_ok=True)
    with open(salida_txt, "w", encoding="utf-8") as f_plano, \
         open(salida_ts, "w", encoding="utf-8") as f_ts:
        for seg in segments:
            texto = correccion.corregir(seg.text.strip(), reglas_correccion)
            f_ts.write(f"[{hms(seg.start)} -> {hms(seg.end)}] {texto}\n")
            f_plano.write(texto + "\n")
            f_plano.flush()
            f_ts.flush()
            if progreso_callback is not None:
                progreso_callback(seg.end, info.duration)
    return info.duration
