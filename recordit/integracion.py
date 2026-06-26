"""Auto-integración de escritorio del AppImage en Linux.

Al ejecutarse como AppImage (variable de entorno APPIMAGE definida), instala una
entrada .desktop y el icono en ~/.local/share para que recordIt aparezca en el
menú/lanzador con su icono. Es idempotente y silenciosa: si algo falla, no rompe
el arranque de la app. (Tras la 1ª integración puede hacer falta reiniciar la
sesión para que el escritorio refresque el icono.)
"""
import os
import shutil
import sys
from pathlib import Path

_INDEX_THEME = (
    "[Icon Theme]\n"
    "Name=hicolor\n"
    "Comment=Fallback icon theme\n"
    "Directories=256x256/apps\n\n"
    "[256x256/apps]\n"
    "Size=256\n"
    "Context=Applications\n"
    "Type=Threshold\n"
)


def _desktop_contenido(appimage: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=recordIt\n"
        "Comment=Grabar, transcribir y generar actas de reunión\n"
        f'Exec="{appimage}" %U\n'
        "Icon=recordit\n"
        "Categories=AudioVideo;Utility;\n"
        "Terminal=false\n"
        "StartupWMClass=recordit\n"
    )


def integrar_escritorio(icono_origen) -> bool:
    """Instala .desktop + icono si se ejecuta como AppImage. Devuelve True si actuó."""
    appimage = os.environ.get("APPIMAGE")
    if not (sys.platform.startswith("linux") and appimage):
        return False
    try:
        home = Path.home()
        apps = home / ".local" / "share" / "applications"
        hicolor = home / ".local" / "share" / "icons" / "hicolor"
        icons = hicolor / "256x256" / "apps"
        apps.mkdir(parents=True, exist_ok=True)
        icons.mkdir(parents=True, exist_ok=True)

        if Path(icono_origen).exists():
            shutil.copyfile(icono_origen, icons / "recordit.png")
        idx = hicolor / "index.theme"
        if not idx.exists():
            idx.write_text(_INDEX_THEME, encoding="utf-8")

        desktop = apps / "recordit.desktop"
        contenido = _desktop_contenido(appimage)
        if not desktop.exists() or desktop.read_text(encoding="utf-8") != contenido:
            desktop.write_text(contenido, encoding="utf-8")

        os.system(f'gtk-update-icon-cache -f -t "{hicolor}" >/dev/null 2>&1')
        os.system(f'update-desktop-database "{apps}" >/dev/null 2>&1')
        return True
    except Exception:  # noqa: BLE001 — nunca debe impedir abrir la app
        return False
