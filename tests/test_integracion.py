from recordit import integracion


def test_no_actua_si_no_es_appimage(monkeypatch, tmp_path):
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert integracion.integrar_escritorio(tmp_path / "x.png") is False


def test_instala_desktop_e_icono(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(integracion.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("APPIMAGE", "/ruta/recordIt-x86_64.AppImage")
    monkeypatch.setattr(integracion.os, "system", lambda cmd: 0)  # no tocar cachés reales
    monkeypatch.setattr(integracion.sys, "platform", "linux")
    icono = tmp_path / "appicon.png"
    icono.write_bytes(b"\x89PNG\r\n\x1a\n")  # cabecera PNG mínima

    assert integracion.integrar_escritorio(icono) is True
    desktop = home / ".local" / "share" / "applications" / "recordit.desktop"
    icon = home / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "recordit.png"
    assert desktop.exists() and icon.exists()
    txt = desktop.read_text(encoding="utf-8")
    assert "/ruta/recordIt-x86_64.AppImage" in txt
    assert "Icon=recordit" in txt
