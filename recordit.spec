# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller recordit.spec
import ctypes.util
import glob
import importlib.util
import os
import re
import sys
from PyInstaller.utils.hooks import collect_all

binarios = []
# ffmpeg empaquetado: ffmpeg.exe en Windows, ffmpeg en Linux (colócalo en vendor/).
ffmpeg_nombre = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
ffmpeg_ruta = os.path.join("vendor", ffmpeg_nombre)
if os.path.exists(ffmpeg_ruta):
    binarios.append((ffmpeg_ruta, "."))

# PortAudio (sounddevice): en Linux NO viene embebido en el wheel, así que hay
# que empaquetar libportaudio.so.2 a mano o el AppImage falla en equipos sin
# libportaudio2 instalado ("OSError: PortAudio library not found"). El runtime
# hook hooks/rthook_portaudio.py se encarga de que sounddevice la encuentre.
# En macOS no hace falta: el wheel trae libportaudio.dylib en
# _sounddevice_data/portaudio-binaries y el hook estándar de sounddevice ya la
# empaqueta ahí, que es donde sounddevice la busca.
if os.name != "nt" and sys.platform != "darwin":
    _pa = None
    _candidatos = []
    for _dir in ("/usr/lib/x86_64-linux-gnu", "/usr/lib", "/usr/local/lib", "/lib"):
        _candidatos += glob.glob(os.path.join(_dir, "libportaudio.so*"))
    if _candidatos:
        _pa = _candidatos[0]
    else:
        _hallada = ctypes.util.find_library("portaudio")
        if _hallada and os.path.isabs(_hallada):
            _pa = _hallada
    if not _pa:
        raise SystemExit(
            "No se encontró libportaudio.so.2. Instálala (apt install libportaudio2) "
            "antes de construir; sounddevice la necesita en el bundle.")
    # Destino "." (raíz de _MEIPASS) con el nombre soname que busca sounddevice.
    binarios.append((_pa, "."))

datas, bins, hiddenimports = collect_all("faster_whisper")
binarios += bins
ct_datas, ct_bins, ct_hidden = collect_all("ctranslate2")
binarios += ct_bins
datas += ct_datas
hiddenimports += ct_hidden
# PyAV (av): faster-whisper lo usa para decodificar audio. av trae CADA módulo
# por duplicado: como extensión compilada (.pyd/.so) y como fuente Cython en "modo
# Python puro" (.py) con el MISMO nombre. Dos problemas que hay que resolver juntos:
#   1) El análisis estático de PyInstaller no ve los submódulos compilados
#      (cimports en C) -> "No module named 'av.frame'" al transcribir.
#   2) Si el .py llega al bundle pero la extensión compilada NO gana, Python importa
#      el .py y al ejecutar `from cython.cimports...` peta con
#      AttributeError('__spec__') (bug de Cython.Shadow). En Windows pasaba con
#      av.dictionary: cargaba el .py en vez del .pyd.
# Solución: recoger TODAS las extensiones compiladas de av como binarios y QUITAR de
# los datos los .py/.pxd que tengan gemelo compilado, para que solo se pueda importar
# la extensión. (Los __init__.py de paquete no tienen gemelo y se conservan.)
av_datas, av_bins, av_hidden = collect_all("av")
_av_dir = os.path.dirname(importlib.util.find_spec("av").origin)
_av_compilados = set()  # (carpeta_destino, nombre_modulo) con extensión compilada
for _raiz, _dirs, _ficheros in os.walk(_av_dir):
    _rel = os.path.relpath(_raiz, _av_dir)
    _dest = "av" if _rel == "." else os.path.join("av", _rel)
    for _f in _ficheros:
        if _f.endswith((".pyd", ".so")):
            _av_compilados.add((_dest, _f.split(".")[0]))
            av_bins.append((os.path.join(_raiz, _f), _dest))


def _av_py_redundante(item):
    _orig, _destino = item
    _base = os.path.basename(_orig)
    if not _base.endswith((".py", ".pxd")):
        return False
    return (_destino, _base[: _base.rindex(".")]) in _av_compilados


av_datas = [_d for _d in av_datas if not _av_py_redundante(_d)]
binarios += av_bins
datas += av_datas
hiddenimports += av_hidden
# Dependencias de faster-whisper que el análisis estático no arrastra completas:
# - onnxruntime: motor de la VAD (vad_filter=True) con binarios/_pybind en 'capi'.
# - tokenizers: extensión nativa (PyO3) del tokenizador.
# - huggingface_hub: descarga el modelo en la 1ª ejecución; usa import perezoso
#   vía __getattr__ de módulo, que en el bundle provocaba AttributeError('__spec__').
for _paquete in ("onnxruntime", "tokenizers", "huggingface_hub"):
    _d, _b, _h = collect_all(_paquete)
    datas += _d
    binarios += _b
    hiddenimports += _h
# CustomTkinter trae temas/JSON como datos que hay que empaquetar.
ck_datas, ck_bins, ck_hidden = collect_all("customtkinter")
binarios += ck_bins
datas += ck_datas
hiddenimports += ck_hidden
# reportlab: genera el PDF del acta (Python puro, sin Node).
rl_datas, rl_bins, rl_hidden = collect_all("reportlab")
binarios += rl_bins
datas += rl_datas
hiddenimports += rl_hidden
# Logo e iconos de la GUI.
datas += [(os.path.join("gui", "assets"), os.path.join("gui", "assets"))]
# Glosario (hotwords) y correcciones de la transcripción.
datas += [(os.path.join("recordit", "glosario.txt"), "recordit")]
datas += [(os.path.join("recordit", "correcciones.txt"), "recordit")]

a = Analysis(
    ["recordit_gui.py"],
    pathex=["."],
    binaries=binarios,
    datas=datas,
    hiddenimports=hiddenimports + ["sounddevice", "anthropic",
                                   "PIL._tkinter_finder", "PIL.ImageTk", "cython"],
    runtime_hooks=[os.path.join("hooks", "rthook_portaudio.py")],
    noarchive=False,
)
pyz = PYZ(a.pure)
# Icono del ejecutable (.ico en Windows, .icns en el .app de macOS; en Linux se
# ignora). None si no existe.
_icono = os.path.join("gui", "assets",
                      "appicon.icns" if sys.platform == "darwin" else "appicon.ico")
_icono = _icono if os.path.exists(_icono) else None

if sys.platform == "darwin":
    # macOS necesita un .app, no un binario suelto: sin Info.plist el sistema
    # deniega el micrófono EN SILENCIO (la grabación sale muda) y la app no
    # aparece en el Dock. Y va en modo carpeta (COLLECT) en vez de one-file
    # porque un one-file extraería ~1 GB de dependencias en cada arranque.
    _version = re.search(
        r'__version__ = "([^"]+)"',
        open(os.path.join("recordit", "__init__.py"), encoding="utf-8").read()).group(1)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="recordIt",
              console=False, disable_windowed_traceback=False, icon=_icono)
    coleccion = COLLECT(exe, a.binaries, a.datas, name="recordIt")
    app = BUNDLE(
        coleccion,
        name="recordIt.app",
        icon=_icono,
        bundle_identifier="io.recordit.app",
        version=_version,
        info_plist={
            "CFBundleName": "recordIt",
            "CFBundleDisplayName": "recordIt",
            "CFBundleShortVersionString": _version,
            "CFBundleVersion": _version,
            # El wheel de onnxruntime (VAD de Whisper) pide macOS 14 o superior.
            "LSMinimumSystemVersion": "14.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "recordIt necesita el micrófono para grabar la reunión.",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="recordIt",
              console=False, disable_windowed_traceback=False, icon=_icono)
