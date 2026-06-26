from recordit import preproceso


def test_construir_orden_incluye_filtro_y_16k():
    orden = preproceso.construir_orden("entrada.wav", "salida.wav", ffmpeg="/usr/bin/ffmpeg")
    assert orden[0] == "/usr/bin/ffmpeg"
    assert "entrada.wav" in orden
    assert "salida.wav" in orden
    assert preproceso.FILTRO_AUDIO in orden
    assert "16000" in orden
    # mono
    assert orden[orden.index("-ac") + 1] == "1"


def test_ruta_ffmpeg_cae_al_path(monkeypatch):
    monkeypatch.setattr(preproceso.shutil, "which", lambda nombre: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preproceso.sys, "frozen", False, raising=False)
    assert preproceso.ruta_ffmpeg() == "/usr/bin/ffmpeg"


def test_ruta_ffmpeg_falla_si_no_existe(monkeypatch):
    monkeypatch.setattr(preproceso.shutil, "which", lambda nombre: None)
    monkeypatch.setattr(preproceso.sys, "frozen", False, raising=False)
    try:
        preproceso.ruta_ffmpeg()
        assert False, "debería lanzar FileNotFoundError"
    except FileNotFoundError:
        pass
