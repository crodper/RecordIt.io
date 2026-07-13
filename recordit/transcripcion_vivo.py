"""Transcripción en vivo mientras se graba.

Consume los bloques int16 que el grabador escribe a disco (vía
``muestras_callback`` de ``audio.grabar``), corta tramos de 60–120 s por el
punto más silencioso, los preprocesa con ffmpeg y los transcribe con los
mismos parámetros que la transcripción clásica. Si algo falla, se apaga solo
y JAMÁS afecta a la grabación: el .wav completo sigue en disco para la
transcripción clásica.
"""
import numpy as np

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
