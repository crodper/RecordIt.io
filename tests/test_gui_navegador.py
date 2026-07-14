"""Saneo de entorno al abrir el navegador desde el ejecutable empaquetado.

El bug: en el .exe/AppImage (PyInstaller), webbrowser lanza el navegador con el
LD_LIBRARY_PATH de las libs incluidas y este muere → el botón «Descargar» no
hacía nada. _entorno_sistema restaura el entorno original durante la llamada.
"""
import os

import gui.app as app


def test_fuera_de_empaquetado_no_toca_entorno(monkeypatch):
    monkeypatch.delattr(app.sys, "frozen", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle/libs")
    with app._entorno_sistema():
        assert os.environ["LD_LIBRARY_PATH"] == "/bundle/libs"


def test_empaquetado_restaura_valor_original(monkeypatch):
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle/libs")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib")
    with app._entorno_sistema():
        # Dentro: el navegador debe ver el entorno del sistema, no el empaquetado.
        assert os.environ["LD_LIBRARY_PATH"] == "/usr/lib"
    # Fuera: se revierte al valor que tenía el proceso empaquetado.
    assert os.environ["LD_LIBRARY_PATH"] == "/bundle/libs"


def test_empaquetado_sin_orig_elimina_variable(monkeypatch):
    # Si el original estaba sin definir, PyInstaller no crea el _ORIG:
    # dentro del contexto la variable debe desaparecer.
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle/libs")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    with app._entorno_sistema():
        assert "LD_LIBRARY_PATH" not in os.environ
    assert os.environ["LD_LIBRARY_PATH"] == "/bundle/libs"
