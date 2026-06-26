#!/usr/bin/env bash
# Crea recordIt-x86_64.AppImage a partir del binario portable (dist-portable/recordIt).
# Requiere haber ejecutado antes ./build-linux.sh (binario sobre glibc antigua).
# Descarga appimagetool si no está. La portabilidad la da el binario portable +
# el runtime de AppImage; el AppImage NO incluye glibc.
set -euo pipefail
cd "$(dirname "$0")"

BIN="dist-portable/recordIt"
[ -f "$BIN" ] || { echo "Falta $BIN. Ejecuta antes ./build-linux.sh" >&2; exit 1; }
[ -f gui/assets/appicon.png ] || { echo "Falta gui/assets/appicon.png" >&2; exit 1; }

TOOL="vendor/appimagetool-x86_64.AppImage"
if [ ! -f "$TOOL" ]; then
  echo "==> Descargando appimagetool…"
  curl -fsSL -o "$TOOL" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi

echo "==> Montando AppDir…"
rm -rf AppDir
mkdir -p AppDir/usr/bin AppDir/usr/share/applications \
         AppDir/usr/share/icons/hicolor/256x256/apps
cp "$BIN" AppDir/usr/bin/recordIt
chmod +x AppDir/usr/bin/recordIt
cp gui/assets/appicon.png AppDir/recordit.png
cp gui/assets/appicon.png AppDir/usr/share/icons/hicolor/256x256/apps/recordit.png

cat > AppDir/recordit.desktop <<'DESK'
[Desktop Entry]
Type=Application
Name=recordIt
Comment=Grabar, transcribir y generar actas de reunión
Exec=recordIt
Icon=recordit
Categories=AudioVideo;Utility;
Terminal=false
DESK
cp AppDir/recordit.desktop AppDir/usr/share/applications/recordit.desktop

cat > AppDir/AppRun <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/recordIt" "$@"
RUN
chmod +x AppDir/AppRun

echo "==> Empaquetando AppImage…"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" AppDir recordIt-x86_64.AppImage

echo "Listo: recordIt-x86_64.AppImage"
