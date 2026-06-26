"""Runtime hook de PyInstaller: que sounddevice encuentre PortAudio embebido.

En Linux sounddevice importa PortAudio vía ``ctypes.util.find_library('portaudio')``,
que solo mira las librerías del sistema y NO el directorio de extracción del
bundle (``sys._MEIPASS``). Como recordit.spec empaqueta libportaudio.so dentro
del bundle, aquí parcheamos find_library para devolver esa ruta y así el AppImage
funciona en equipos sin libportaudio2 instalado.

PyInstaller ejecuta los runtime hooks antes del código de usuario, o sea antes de
que gui/app.py importe sounddevice.
"""
import ctypes.util
import glob
import os
import sys

_base = getattr(sys, "_MEIPASS", None)
if _base:
    _coincidencias = glob.glob(os.path.join(_base, "libportaudio.so*"))
    if _coincidencias:
        _lib = _coincidencias[0]
        _original = ctypes.util.find_library

        def find_library(nombre):
            if nombre == "portaudio":
                return _lib
            return _original(nombre)

        ctypes.util.find_library = find_library
