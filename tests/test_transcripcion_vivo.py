import numpy as np

from recordit import transcripcion_vivo

F = 1000  # Hz ficticios: tests rápidos e independientes del audio real


def _senal(duracion_s, amplitud=1000):
    return np.full(int(duracion_s * F), amplitud, dtype=np.int16)


def test_punto_de_corte_none_si_no_hay_suficiente_audio():
    assert transcripcion_vivo.punto_de_corte(_senal(90), F) is None


def test_punto_de_corte_elige_el_silencio():
    ruido = _senal(130)
    ruido[80 * F:81 * F] = 0  # 1 s de silencio en el segundo 80
    corte = transcripcion_vivo.punto_de_corte(ruido, F)
    assert 80 * F <= corte <= 81 * F


def test_punto_de_corte_sin_silencio_corta_dentro_de_la_ventana():
    corte = transcripcion_vivo.punto_de_corte(_senal(130), F)
    assert 60 * F <= corte <= 120 * F
