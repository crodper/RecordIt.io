#!/usr/bin/env bash
# Construye recordIt.app en macOS con PyInstaller y lo comprime para distribuir.
# Requisitos previos: ejecutarlo desde la raíz del repo, con el venv ya creado y
# las dependencias instaladas (ver docs/BUILD-MACOS.md). Necesita vendor/ffmpeg.
#
# Uso:  ./build-macos.sh
set -euo pipefail
cd "$(dirname "$0")"

[[ "$(uname -s)" == "Darwin" ]] || {
  echo "Este script solo funciona en macOS (PyInstaller no cruza de SO)." >&2
  exit 1
}
[[ -f vendor/ffmpeg ]] || {
  echo "Falta vendor/ffmpeg (binario estático de macOS). Ver docs/BUILD-MACOS.md." >&2
  exit 1
}

PY=".venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

"$PY" -m PyInstaller --noconfirm --clean recordit.spec

# ditto y no zip: conserva los enlaces internos del .app y la firma ad-hoc que
# pone PyInstaller (obligatoria en Apple Silicon para que el binario arranque).
ARCH="$(uname -m)"
ditto -c -k --keepParent dist/recordIt.app "dist/recordIt-macos-${ARCH}.zip"
echo "Listo: dist/recordIt.app y dist/recordIt-macos-${ARCH}.zip"
