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


import shutil
from types import SimpleNamespace

from recordit import rutas, transcripcion


class _ModeloFake:
    """Devuelve un segmento por tramo con la duración real del tramo."""

    def __init__(self):
        self.llamadas = 0

    def transcribe(self, audio, **kwargs):
        import wave
        with wave.open(str(audio)) as w:
            dur = w.getnframes() / w.getframerate()
        self.llamadas += 1
        segs = [SimpleNamespace(start=0.0, end=dur, text=f" tramo{self.llamadas} ")]
        return iter(segs), SimpleNamespace(duration=dur)


def _copiar(entrada, salida):
    shutil.copy(entrada, salida)


def _vivo(base, monkeypatch, tmp_path, **kwargs):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    return transcripcion_vivo.TranscriptorEnVivo(
        base, F, min_tramo_s=2.0, max_tramo_s=4.0,
        preprocesar=_copiar, cargar_modelo=_ModeloFake, hotwords="", **kwargs)


def test_vivo_transcribe_tramos_con_offset(monkeypatch, tmp_path):
    vivo = _vivo("reunion_x", monkeypatch, tmp_path)
    # 6 s de audio con min=2/max=4: un corte (~2.25 s, señal constante → corta
    # al principio de la ventana) + el resto al finalizar → exactamente 2 tramos.
    for _ in range(6):
        vivo.alimentar(_senal(1).tobytes())
    assert vivo.finalizar() is True
    ts = rutas.ruta_timestamps("reunion_x").read_text(encoding="utf-8")
    txt = rutas.ruta_transcripcion("reunion_x").read_text(encoding="utf-8")
    assert txt.splitlines() == ["tramo1", "tramo2"]
    # el 2º tramo arranca donde terminó el 1º (offset acumulado, no 00:00:00)
    lineas = ts.splitlines()
    assert lineas[0].startswith("[00:00:00 -> ")
    assert not lineas[1].startswith("[00:00:00 -> ")
    assert abs(vivo.duracion - 6.0) < 0.5


def test_vivo_formato_identico_a_la_transcripcion_clasica(monkeypatch, tmp_path):
    vivo = _vivo("reunion_fmt", monkeypatch, tmp_path)
    vivo.alimentar(_senal(3).tobytes())
    assert vivo.finalizar() is True
    ts = rutas.ruta_timestamps("reunion_fmt").read_text(encoding="utf-8")
    # mismo formato exacto que transcripcion.transcribir: "[HH:MM:SS -> HH:MM:SS] texto"
    assert ts.startswith("[00:00:00 -> 00:00:03] tramo1")


def test_vivo_error_en_el_worker_no_revienta_y_finalizar_es_false(monkeypatch, tmp_path):
    def preprocesar_roto(entrada, salida):
        raise RuntimeError("ffmpeg caput")
    vivo = _vivo("reunion_err", monkeypatch, tmp_path, )
    vivo._preprocesar = preprocesar_roto
    vivo.alimentar(_senal(5).tobytes())  # supera max_tramo_s=4 → intenta procesar
    assert vivo.finalizar() is False
    vivo.alimentar(_senal(1).tobytes())  # tras el error, alimentar no lanza


def test_crear_devuelve_none_sin_modelo_en_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert transcripcion_vivo.crear("reunion_x", 44100) is None


def test_crear_devuelve_transcriptor_con_modelo_en_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(transcripcion, "modelo_en_cache", lambda m="large-v3": True)
    vivo = transcripcion_vivo.crear("reunion_x", 44100)
    assert isinstance(vivo, transcripcion_vivo.TranscriptorEnVivo)
    vivo.finalizar()
