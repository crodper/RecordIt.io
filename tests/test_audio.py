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
