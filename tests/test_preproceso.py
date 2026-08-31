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


def test_ruta_ffmpeg_busca_las_rutas_de_macos(monkeypatch, tmp_path):
    # Un .app lanzado desde Finder no hereda el PATH del shell, así que no ve el
    # ffmpeg de Homebrew: hay que mirar sus rutas a mano.
    falso = tmp_path / "ffmpeg"
    falso.write_text("")
    monkeypatch.setattr(preproceso.sys, "platform", "darwin")
    monkeypatch.setattr(preproceso, "FFMPEG_MAC", (str(falso),))
    monkeypatch.setattr(preproceso.shutil, "which", lambda nombre: None)
    monkeypatch.setattr(preproceso.sys, "frozen", False, raising=False)
    assert preproceso.ruta_ffmpeg() == str(falso)


def test_ruta_ffmpeg_no_usa_las_rutas_de_macos_en_linux(monkeypatch, tmp_path):
    falso = tmp_path / "ffmpeg"
    falso.write_text("")
    monkeypatch.setattr(preproceso.sys, "platform", "linux")
    monkeypatch.setattr(preproceso, "FFMPEG_MAC", (str(falso),))
    monkeypatch.setattr(preproceso.shutil, "which", lambda nombre: None)
    monkeypatch.setattr(preproceso.sys, "frozen", False, raising=False)
    try:
        preproceso.ruta_ffmpeg()
        assert False, "debería lanzar FileNotFoundError"
    except FileNotFoundError:
        pass
