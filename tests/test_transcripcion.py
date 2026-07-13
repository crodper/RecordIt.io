from types import SimpleNamespace

from recordit import transcripcion


class _ModeloFake:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        segs = [SimpleNamespace(start=0.0, end=1.0, text=" Hola "),
                SimpleNamespace(start=1.0, end=2.0, text=" mundo ")]
        info = SimpleNamespace(duration=2.0)
        return iter(segs), info


def test_transcribir_escribe_ficheros_y_pasa_parametros(tmp_path):
    txt = tmp_path / "transcripcion.txt"
    ts = tmp_path / "transcripcion_timestamps.txt"
    modelo = _ModeloFake()
    duracion = transcripcion.transcribir(
        "audio.wav", txt, ts, modelo_cargado=modelo)
    assert duracion == 2.0
    assert txt.read_text(encoding="utf-8") == "Hola\nmundo\n"
    assert "[00:00:00 -> 00:00:01] Hola" in ts.read_text(encoding="utf-8")
    # decisiones anti-alucinación que NO deben perderse
    assert modelo.kwargs["language"] == "es"
    assert modelo.kwargs["vad_filter"] is True
    assert modelo.kwargs["condition_on_previous_text"] is False


def test_hotwords_explicito_se_pasa_al_modelo(tmp_path):
    modelo = _ModeloFake()
    transcripcion.transcribir(
        "audio.wav", tmp_path / "t.txt", tmp_path / "ts.txt",
        modelo_cargado=modelo, hotwords="Modbus, Zigbee")
    assert modelo.kwargs["hotwords"] == "Modbus, Zigbee"


def test_hotwords_vacio_se_desactiva(tmp_path):
    modelo = _ModeloFake()
    transcripcion.transcribir(
        "audio.wav", tmp_path / "t.txt", tmp_path / "ts.txt",
        modelo_cargado=modelo, hotwords="")
    assert modelo.kwargs["hotwords"] is None


def test_hotwords_por_defecto_usa_glosario(tmp_path):
    modelo = _ModeloFake()
    transcripcion.transcribir(
        "audio.wav", tmp_path / "t.txt", tmp_path / "ts.txt",
        modelo_cargado=modelo)
    # sin pasar hotwords, debe inyectar el glosario del repo (incluye "Modbus")
    assert "Modbus" in modelo.kwargs["hotwords"]


def test_modelo_en_cache_falso_si_no_existe(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert transcripcion.modelo_en_cache("large-v3") is False


def test_progreso_callback_se_invoca(tmp_path):
    llamadas = []
    transcripcion.transcribir(
        "audio.wav", tmp_path / "t.txt", tmp_path / "ts.txt",
        modelo_cargado=_ModeloFake(),
        progreso_callback=lambda actual, total: llamadas.append((actual, total)))
    assert llamadas[-1] == (2.0, 2.0)


def test_iterar_segmentos_es_la_unica_fuente_de_parametros():
    modelo = _ModeloFake()
    segs, info = transcripcion.iterar_segmentos("audio.wav", modelo, "Modbus")
    assert info.duration == 2.0
    assert [s.text.strip() for s in segs] == ["Hola", "mundo"]
    assert modelo.kwargs["language"] == "es"
    assert modelo.kwargs["beam_size"] == 5
    assert modelo.kwargs["vad_filter"] is True
    assert modelo.kwargs["vad_parameters"] == dict(min_silence_duration_ms=500)
    assert modelo.kwargs["condition_on_previous_text"] is False
    assert modelo.kwargs["temperature"] == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    assert modelo.kwargs["hotwords"] == "Modbus"


def test_iterar_segmentos_hotwords_vacio_pasa_none():
    modelo = _ModeloFake()
    transcripcion.iterar_segmentos("audio.wav", modelo, "")
    assert modelo.kwargs["hotwords"] is None
