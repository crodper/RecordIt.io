#!/usr/bin/env bash
# Build PORTABLE para Linux: construye dentro de un contenedor con glibc antigua
# (Debian bullseye, glibc 2.31) para que el ejecutable arranque en la mayoría de
# distros. Construir en el host (glibc nueva) produce un binario que falla en
# equipos antiguos con "GLIBC_x.y not found".
#
# Salida: dist-portable/recordIt
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f vendor/ffmpeg ]; then
  echo "Falta vendor/ffmpeg (binario estático de Linux). Descárgalo antes de construir." >&2
  exit 1
fi

docker build -t recordit-build -f Dockerfile.linux .
docker run --rm -v "$PWD":/app -w /app recordit-build \
  pyinstaller --noconfirm --clean --distpath dist-portable --workpath /tmp/wb recordit.spec

echo "Listo: dist-portable/recordIt (portable; glibc antigua)"
