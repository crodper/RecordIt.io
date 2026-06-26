#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f vendor/ffmpeg ]; then
  echo "Falta vendor/ffmpeg (binario estático de Linux). Descárgalo antes de construir." >&2
  exit 1
fi
.venv/bin/pyinstaller recordit.spec
echo "Listo: dist/recordIt"
