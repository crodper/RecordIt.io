import threading
import wave

import numpy as np

from recordit import audio


def test_dbfs_valores_extremos():
    assert audio.dbfs(1.0) == 0.0
    assert audio.dbfs(0.0) == -120.0


def test_agc_no_satura():
    agc = audio.GananciaAutomatica()
    bloque = np.full(1024, 0.05, dtype=np.float32)  # señal floja
    salida = agc.procesar(bloque)
    assert salida.max() <= 1.0
    assert salida.min() >= -1.0


def test_agc_amplifica_senal_floja():
    agc = audio.GananciaAutomatica()
    bloque = np.full(1024, 0.02, dtype=np.float32)
    for _ in range(50):  # el AGC sube despacio (release lento)
        agc.procesar(bloque)
    assert agc.ganancia_db > 0.0


def test_nombre_archivo_formato():
    nombre = audio.nombre_archivo()
    assert nombre.startswith("reunion_")
    assert nombre.endswith(".wav")


# --- remuestreo -------------------------------------------------------------


def test_remuestrear_misma_frecuencia_es_identidad():
    x = np.array([0, 100, -100, 32767, -32768], dtype=np.int16)
    y = audio.remuestrear(x, 48000, 48000)
    assert np.array_equal(y, x)


def test_remuestrear_reduce_longitud_a_la_mitad():
    x = np.arange(1000, dtype=np.int16)
    y = audio.remuestrear(x, 48000, 24000)
    assert abs(len(y) - 500) <= 1
    assert y.dtype == np.int16


def test_remuestrear_conserva_rango_int16():
    x = np.full(1000, 30000, dtype=np.int16)
    y = audio.remuestrear(x, 48000, 16000)
    assert y.max() <= 32767 and y.min() >= -32768
    assert abs(int(y[len(y) // 2]) - 30000) <= 1  # meseta se conserva


# --- mezcla micro + salida --------------------------------------------------


def test_mezclar_suma_ambos_lados():
    mic = np.array([100, 200, 300], dtype=np.int16)
    sal = np.array([10, 20, 30], dtype=np.int16)
    assert np.array_equal(audio.mezclar(mic, sal), np.array([110, 220, 330]))


def test_mezclar_recorta_al_pico_maximo():
    mic = np.array([30000, -30000], dtype=np.int16)
    sal = np.array([30000, -30000], dtype=np.int16)
    m = audio.mezclar(mic, sal)
    assert m[0] == 32767 and m[1] == -32768


def test_mezclar_rellena_salida_corta_con_ceros():
    mic = np.array([100, 200, 300, 400], dtype=np.int16)
    sal = np.array([10, 20], dtype=np.int16)
    assert np.array_equal(audio.mezclar(mic, sal), np.array([110, 220, 300, 400]))


def test_mezclar_trunca_salida_larga():
    mic = np.array([100, 200], dtype=np.int16)
    sal = np.array([10, 20, 30, 40], dtype=np.int16)
    assert np.array_equal(audio.mezclar(mic, sal), np.array([110, 220]))


def test_mezclar_salida_vacia_devuelve_mic():
    mic = np.array([100, 200], dtype=np.int16)
    sal = np.zeros(0, dtype=np.int16)
    assert np.array_equal(audio.mezclar(mic, sal), mic)


# --- selección de micrófonos -------------------------------------------------

# Host APIs y dispositivos tal como los expone PortAudio en un equipo PipeWire
# real (capturado con sounddevice). Sirven de fixture para la función pura.
HOSTAPIS_PIPEWIRE = [{"name": "ALSA"}, {"name": "OSS"}, {"name": "PulseAudio"}]


def _dev(nombre, ent, sal, api):
    return {"name": nombre, "max_input_channels": ent,
            "max_output_channels": sal, "hostapi": api}


# Réplica del `query_devices()` real (índices coinciden con la posición).
DISPOSITIVOS_PIPEWIRE = [
    _dev("sof-soundwire: - (hw:0,0)", 0, 2, 0),
    _dev("sof-soundwire: - (hw:0,1)", 2, 0, 0),
    _dev("sof-soundwire: - (hw:0,2)", 0, 2, 0),
    _dev("sof-soundwire: 24B3HMA2 (hw:0,5)", 0, 2, 0),
    _dev("sof-soundwire: HDMI 2 (hw:0,6)", 0, 8, 0),
    _dev("sof-soundwire: HDMI 3 (hw:0,7)", 0, 8, 0),
    _dev("sof-soundwire: - (hw:0,31)", 0, 2, 0),
    _dev("sysdefault", 0, 128, 0),
    _dev("hdmi", 0, 2, 0),
    _dev("pipewire", 128, 128, 0),
    _dev("dmix", 0, 2, 0),
    _dev("default", 128, 128, 0),
    _dev("Default Sink", 0, 32, 2),
    _dev("Default Source", 32, 0, 2),
    _dev("bluez_output.40:72:18:32:F9:5A", 0, 2, 2),
    _dev("alsa_output...HDMI3__sink", 0, 2, 2),
    _dev("alsa_output...HDMI2__sink", 0, 2, 2),
    _dev("alsa_output...HDMI1__sink", 0, 2, 2),
    _dev("alsa_output...Headphones__sink", 0, 2, 2),
    _dev("bluez_input.40:72:18:32:F9:5A", 1, 0, 2),
    _dev("bluez_output.40:72:18:32:F9:5A.monitor", 2, 0, 2),
    _dev("alsa_output...HDMI3__sink.monitor", 2, 0, 2),
    _dev("alsa_output...HDMI2__sink.monitor", 2, 0, 2),
    _dev("alsa_output...HDMI1__sink.monitor", 2, 0, 2),
    _dev("alsa_output...Headphones__sink.monitor", 2, 0, 2),
    _dev("alsa_input.pci-0000_00_1f.3-platform-sof_sdw.HiFi__Mic__source", 2, 0, 2),
]


def test_microfonos_colapsa_duplicados_en_pipewire():
    # En un sistema con PulseAudio/PipeWire, los 26 dispositivos crudos se
    # reducen a los micros reales: predeterminado del sistema + integrado + BT.
    micros = audio.seleccionar_microfonos(
        DISPOSITIVOS_PIPEWIRE, HOSTAPIS_PIPEWIRE, predeterminado=11)
    nombres = [nom for _, _, nom in micros]
    assert "Default Source" in nombres
    assert "bluez_input.40:72:18:32:F9:5A" in nombres
    assert any("Mic__source" in n for n in nombres)
    # No deben aparecer los duplicados crudos ALSA ni los routers genéricos.
    assert not any("hw:0,1" in n for n in nombres)
    assert "pipewire" not in nombres
    assert "default" not in nombres
    assert len(micros) == 3


def test_microfonos_no_incluye_monitores():
    micros = audio.seleccionar_microfonos(
        DISPOSITIVOS_PIPEWIRE, HOSTAPIS_PIPEWIRE, predeterminado=11)
    assert not any("monitor" in nom.lower() for _, _, nom in micros)


def test_microfonos_etiquetas_amigables():
    micros = audio.seleccionar_microfonos(
        DISPOSITIVOS_PIPEWIRE, HOSTAPIS_PIPEWIRE, predeterminado=11)
    etiqueta = {nom: etq for _, etq, nom in micros}
    assert "Bluetooth" in etiqueta["bluez_input.40:72:18:32:F9:5A"]
    assert "integrado" in etiqueta[
        "alsa_input.pci-0000_00_1f.3-platform-sof_sdw.HiFi__Mic__source"].lower()
    # El predeterminado del sistema se marca como tal.
    assert "predeterminado" in etiqueta["Default Source"].lower()


def test_microfonos_alsa_puro_no_se_filtra_de_mas():
    # Sin PulseAudio (ALSA puro), se conservan las entradas reales (sin monitores).
    hostapis = [{"name": "ALSA"}]
    dispositivos = [
        _dev("sof-soundwire: - (hw:0,1)", 2, 0, 0),
        _dev("default", 128, 128, 0),
        _dev("sof-soundwire: - (hw:0,0)", 0, 2, 0),  # sin entrada -> fuera
    ]
    micros = audio.seleccionar_microfonos(dispositivos, hostapis, predeterminado=0)
    nombres = [nom for _, _, nom in micros]
    assert "sof-soundwire: - (hw:0,1)" in nombres
    assert "default" in nombres
    assert len(micros) == 2


# --- selección de la salida del sistema -------------------------------------


def test_salidas_linux_lista_los_monitores():
    salidas = audio.seleccionar_salidas(
        DISPOSITIVOS_PIPEWIRE, HOSTAPIS_PIPEWIRE, nombre_sink_defecto=None)
    nombres = [nom for _, _, nom, _ in salidas]
    assert all(".monitor" in n for n in nombres)
    assert "alsa_output...Headphones__sink.monitor" in nombres
    assert all(loop is False for _, _, _, loop in salidas)  # Linux: no loopback


def test_salidas_linux_pone_el_sink_por_defecto_primero():
    salidas = audio.seleccionar_salidas(
        DISPOSITIVOS_PIPEWIRE, HOSTAPIS_PIPEWIRE,
        nombre_sink_defecto="alsa_output...Headphones__sink")
    assert salidas[0][2] == "alsa_output...Headphones__sink.monitor"


def test_salidas_windows_usa_wasapi_loopback():
    hostapis = [{"name": "MME"}, {"name": "Windows WASAPI"}]
    dispositivos = [
        _dev("Micro (Realtek)", 2, 0, 1),
        _dev("Altavoces (Realtek)", 0, 2, 1),
        _dev("Auriculares (USB)", 0, 2, 1),
    ]
    salidas = audio.seleccionar_salidas(dispositivos, hostapis,
                                        nombre_sink_defecto="Altavoces (Realtek)")
    nombres = [nom for _, _, nom, _ in salidas]
    assert "Micro (Realtek)" not in nombres  # solo dispositivos de salida
    assert "Altavoces (Realtek)" in nombres
    assert all(loop is True for _, _, _, loop in salidas)  # Windows: loopback
    assert salidas[0][2] == "Altavoces (Realtek)"  # el sink por defecto primero


def test_salidas_alsa_puro_sin_monitores_es_vacio():
    hostapis = [{"name": "ALSA"}]
    dispositivos = [_dev("sof-soundwire: - (hw:0,1)", 2, 0, 0),
                    _dev("default", 128, 128, 0)]
    assert audio.seleccionar_salidas(dispositivos, hostapis) == []


# --- listar salidas y salida por defecto -----------------------------------


def test_salida_sistema_por_defecto_devuelve_indice_y_loopback(monkeypatch):
    monkeypatch.setattr(audio, "listar_salidas",
                        lambda reescanear=False: [(7, "etq", "spk.monitor", False),
                                                  (9, "etq2", "otro.monitor", False)])
    assert audio.salida_sistema_por_defecto() == (7, False)


def test_salida_sistema_por_defecto_none_si_no_hay(monkeypatch):
    monkeypatch.setattr(audio, "listar_salidas", lambda reescanear=False: [])
    assert audio.salida_sistema_por_defecto() is None


# --- grabación con callback ---------------------------------------------------


class _StreamFake:
    """InputStream falso parametrizable por dispositivo.

    Entrega `n_bloques` bloques al entrar en el `with`. El micro (device=None)
    entrega el valor `mic`; cualquier otro device entrega el valor `salida`.
    """

    mic = 1000
    salida = 2000
    canales_salida = 2
    instancias = []  # todas las instancias creadas (para inspeccionar en los tests)

    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.device = kwargs.get("device")
        self.channels = kwargs.get("channels", 1)
        self.cerrado = False
        _StreamFake.instancias.append(self)

    def __enter__(self):
        es_salida = self.device is not None
        valor = _StreamFake.salida if es_salida else _StreamFake.mic
        datos = np.full((1024, self.channels), valor, dtype=np.int16)
        for _ in range(3):
            self.callback(datos, 1024, None, None)
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        self.cerrado = True


def test_grabar_entrega_los_bytes_escritos_a_muestras_callback(tmp_path, monkeypatch):
    monkeypatch.setattr(audio.sd, "InputStream", _StreamFake)
    monkeypatch.setattr(audio, "frecuencia_soportada", lambda d, f, c: f)
    recibidos = []
    audio.grabar(tmp_path / "x.wav", evento_parada=threading.Event(),
                 duracion_max=0.0, ganancia=1.0,
                 muestras_callback=recibidos.append)
    assert recibidos, "el callback no recibió ningún bloque"
    with wave.open(str(tmp_path / "x.wav")) as w:
        escrito = w.readframes(w.getnframes())
    assert b"".join(recibidos) == escrito


def test_grabar_mezcla_micro_y_salida(tmp_path, monkeypatch):
    monkeypatch.setattr(audio.sd, "InputStream", _StreamFake)
    monkeypatch.setattr(audio, "frecuencia_soportada", lambda d, f, c: f)
    monkeypatch.setattr(audio.sd, "query_devices",
                        lambda d=None, k=None: {"max_output_channels": 2,
                                                "default_samplerate": 44100})
    recibidos = []
    audio.grabar(tmp_path / "x.wav", evento_parada=threading.Event(),
                 duracion_max=0.0, ganancia=1.0, fuente_salida=5,
                 muestras_callback=recibidos.append)
    muestras = np.frombuffer(b"".join(recibidos), dtype=np.int16)
    # mic (1000 -> 999 por el redondeo float32 del pipeline de ganancia fija,
    # preexistente y ajeno a esta tarea) + salida downmezclada a mono (2000)
    # = 2999 en cada muestra.
    assert muestras.size > 0
    assert set(np.unique(muestras)) == {2999}


class _StreamFakeSalidaFallaAlArrancar(_StreamFake):
    """Como `_StreamFake`, pero el stream de salida lanza al hacer `__enter__`.

    Simula un segundo stream que CONSTRUYE bien (no hay excepción en
    `sd.InputStream(...)`) pero falla al arrancar (p. ej. dispositivo WASAPI
    ocupado): el fallo real ocurre en `.start()`, dentro del `with`.
    """

    def __enter__(self):
        if self.device is not None:
            raise RuntimeError("dispositivo de salida ocupado")
        return super().__enter__()


def test_grabar_no_se_cae_si_la_salida_falla_al_arrancar(tmp_path, monkeypatch):
    monkeypatch.setattr(audio.sd, "InputStream", _StreamFakeSalidaFallaAlArrancar)
    monkeypatch.setattr(audio, "frecuencia_soportada", lambda d, f, c: f)
    monkeypatch.setattr(audio.sd, "query_devices",
                        lambda d=None, k=None: {"max_output_channels": 2,
                                                "default_samplerate": 44100})
    llamadas = []
    monkeypatch.setattr(audio.registro, "registrar_excepcion",
                        lambda contexto: llamadas.append(contexto))
    antes = len(_StreamFake.instancias)
    recibidos = []
    audio.grabar(tmp_path / "x.wav", evento_parada=threading.Event(),
                 duracion_max=0.0, ganancia=1.0, fuente_salida=5,
                 muestras_callback=recibidos.append)
    assert llamadas, "registro.registrar_excepcion no se llamó"
    muestras = np.frombuffer(b"".join(recibidos), dtype=np.int16)
    assert muestras.size > 0
    # Solo micro (999 tras el redondeo del pipeline de ganancia), sin mezclar.
    assert set(np.unique(muestras)) == {999}
    nuevas = _StreamFake.instancias[antes:]
    salidas = [inst for inst in nuevas if inst.device is not None]
    assert salidas, "no se creó el stream de salida"
    assert salidas[-1].cerrado, "el stream de salida no se cerró tras fallar al arrancar"
