#!/usr/bin/env bash
# Integra recordIt en el escritorio (icono en el menú/lanzador). Ejecútalo UNA vez
# en la máquina destino, junto al AppImage o pasándole su ruta:
#   ./instalar.sh                      # busca recordIt-x86_64.AppImage al lado
#   ./instalar.sh /ruta/recordIt-x86_64.AppImage
set -euo pipefail

AI="${1:-}"
[ -z "$AI" ] && AI="$(dirname "$(readlink -f "$0")")/recordIt-x86_64.AppImage"
AI="$(readlink -f "$AI")"
[ -f "$AI" ] || { echo "No encuentro el AppImage. Uso: ./instalar.sh /ruta/recordIt-x86_64.AppImage" >&2; exit 1; }
chmod +x "$AI"

APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$APPS" "$ICONS"

# Extraer el icono embebido del propio AppImage.
tmp="$(mktemp -d)"
( cd "$tmp" && APPIMAGE_EXTRACT_AND_RUN=1 "$AI" --appimage-extract recordit.png >/dev/null 2>&1 || true )
if [ -f "$tmp/squashfs-root/recordit.png" ]; then
  cp "$tmp/squashfs-root/recordit.png" "$ICONS/recordit.png"
fi
rm -rf "$tmp"

cat > "$APPS/recordit.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=recordIt
Comment=Grabar, transcribir y generar actas de reunión
Exec="$AI"
Icon=recordit
Categories=AudioVideo;Utility;
Terminal=false
StartupWMClass=recordit
EOF
chmod +x "$APPS/recordit.desktop"

update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Listo. Busca «recordIt» en el menú de aplicaciones."
echo "(Si no aparece de inmediato, cierra y vuelve a abrir la sesión.)"
