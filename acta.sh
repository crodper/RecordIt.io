#!/usr/bin/env bash
#
# acta.sh — Flujo completo: audio de reunión -> acta en Markdown y PDF.
#
# Encadena:
#   1. Preprocesado del audio con ffmpeg (denoise + normalize + 16 kHz mono).
#   2. Transcripción con faster-whisper large-v3 (transcribir.py).
#   3. Redacción del acta con el CLI de Claude (claude -p), en Markdown con front-matter.
#   4. Render a PDF con la plantilla (pdf-template/render.mjs).
#
# Uso:
#   ./acta.sh grabaciones/reunion_2026-06-16_10-06-12.wav
#   ./acta.sh grabaciones/reunion.wav "Título personalizado del acta"
#
# Salidas (en ./transcripciones/<base>/, una carpeta por grabación):
#   transcripcion.txt             transcripción en texto plano
#   transcripcion_timestamps.txt  transcripción con marcas de tiempo
#   acta.md                       acta en Markdown (con front-matter)
#   acta.pdf                      acta en PDF
#   clean_16k.wav                 audio preprocesado (intermedio)

set -euo pipefail

# --- Configuración ------------------------------------------------------------
PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$PROYECTO/.venv/bin/python"
TRANSCRIBIR="$PROYECTO/transcribir.py"
SALIDA_DIR="$PROYECTO/transcripciones"
# Plantilla PDF vendorizada dentro del repo. Se puede sobrescribir con PDF_TEMPLATE_DIR.
PLANTILLA_DIR="${PDF_TEMPLATE_DIR:-$PROYECTO/pdf-template}"

# --- Argumentos ---------------------------------------------------------------
if [ $# -lt 1 ]; then
  echo "Uso: $0 <audio.wav> [\"Título del acta\"]" >&2
  exit 1
fi

AUDIO="$1"
TITULO_OVERRIDE="${2:-}"

if [ ! -f "$AUDIO" ]; then
  echo "Error: no existe el fichero de audio «$AUDIO»." >&2
  exit 1
fi

for cmd in ffmpeg node "$PYTHON"; do
  command -v "$cmd" >/dev/null 2>&1 || [ -x "$cmd" ] || { echo "Error: falta «$cmd»." >&2; exit 1; }
done
command -v claude >/dev/null 2>&1 || { echo "Error: falta el CLI «claude» en el PATH." >&2; exit 1; }

BASE="$(basename "$AUDIO")"; BASE="${BASE%.*}"
# Una carpeta por grabación dentro de transcripciones/.
REUNION_DIR="$SALIDA_DIR/$BASE"
mkdir -p "$REUNION_DIR"

LIMPIO="$REUNION_DIR/clean_16k.wav"
TXT="$REUNION_DIR/transcripcion.txt"
ACTA_MD="$REUNION_DIR/acta.md"
ACTA_PDF="$REUNION_DIR/acta.pdf"

# Fecha legible: intenta extraerla del nombre (reunion_AAAA-MM-DD_...), si no, hoy.
if [[ "$BASE" =~ ([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
  FECHA_ISO="${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
else
  FECHA_ISO="$(date +%Y-%m-%d)"
fi
FECHA_LEGIBLE="$(date -d "$FECHA_ISO" +'%-d de %B de %Y' 2>/dev/null || echo "$FECHA_ISO")"

echo "==> [1/4] Preprocesando audio con ffmpeg..."
ffmpeg -y -loglevel error -i "$AUDIO" \
  -af "highpass=f=80,lowpass=f=8000,afftdn=nf=-25,dynaudnorm=f=150:g=15" \
  -ar 16000 -ac 1 -c:a pcm_s16le "$LIMPIO"

echo "==> [2/4] Transcribiendo con faster-whisper large-v3 (puede tardar en CPU)..."
"$PYTHON" "$TRANSCRIBIR" "$LIMPIO" "$TXT"

echo "==> [3/4] Redactando el acta con Claude..."
# Vocabulario canónico (mismo glosario que los hotwords) para que Claude
# normalice nombres de producto al redactar. Vacío si el glosario está vacío.
GLOSARIO_BLOQUE="$(cd "$PROYECTO" && "$PYTHON" -m recordit.glosario --prompt 2>/dev/null || true)"
PROMPT="Eres un asistente que redacta actas de reunión en español a partir de una transcripción automática.

Datos de esta reunión:
- Fecha: $FECHA_LEGIBLE
- Fichero de audio: grabaciones/${BASE}.wav
- Transcripción: transcripciones/${BASE}/transcripcion.txt (Whisper large-v3)

A continuación, tras la línea '=== TRANSCRIPCIÓN ===', tienes la transcripción completa.

Redacta un ACTA DE REUNIÓN en Markdown siguiendo EXACTAMENTE estas reglas:
1. Empieza con un front-matter YAML con estos campos (sin comillas extra):
---
title: \"${TITULO_OVERRIDE:-Acta de reunión — <pon aquí un título corto y descriptivo del tema principal>}\"
audiencia: \"<a quién va dirigida, p. ej. Equipo de producto / desarrollo>\"
estado: \"Acta interna — revisar antes de difundir\"
tags: [acta, <2-4 etiquetas en minúscula sin tildes>]
---
2. Tras el front-matter, un título H1 igual al 'title'.
3. Una tabla inicial con: Fecha, Duración (si se deduce), Audio, Transcripción.
4. Una nota (formato '> **Nota:**') avisando de que el audio es de un solo canal sin diarización, por lo que NO se atribuyen frases a personas; lista las personas mencionadas si las hay; indica que los tramos dudosos van marcados como '(dudoso)'.
5. Cuerpo organizado por TEMAS con encabezados (## 1. ..., ## 2. ...), en viñetas.
6. Sección '## Decisiones tomadas' (lista numerada).
7. Sección '## Acciones pendientes (action items)' como tabla con columnas: # | Acción | Responsable | Plazo (usa '—' si no consta).
8. Sección '## Calendario resumido' si hay fechas relevantes.

Reglas de contenido:
- NO inventes información que no esté en la transcripción. Marca lo dudoso como '(dudoso)'.
- NO atribuyas frases a personas concretas.
- Devuelve ÚNICAMENTE el Markdown del acta (empezando por '---' del front-matter). No añadas explicaciones ni texto antes o después.
${GLOSARIO_BLOQUE:+
$GLOSARIO_BLOQUE
}
=== TRANSCRIPCIÓN ===
$(cat "$TXT")"

claude -p "$PROMPT" > "$ACTA_MD"

# Salvaguarda: si Claude envolvió la respuesta en ```markdown ... ```, lo quitamos.
if head -1 "$ACTA_MD" | grep -q '^```'; then
  sed -i '1d' "$ACTA_MD"
  sed -i '$ { /^```$/d }' "$ACTA_MD"
fi

if ! head -1 "$ACTA_MD" | grep -q '^---'; then
  echo "Aviso: el acta generada no empieza con front-matter YAML; revisa «$ACTA_MD»." >&2
fi

echo "==> [4/4] Generando PDF con la plantilla..."
if [ ! -d "$PLANTILLA_DIR/node_modules" ]; then
  echo "Error: faltan dependencias de la plantilla PDF." >&2
  echo "       Ejecuta una vez: (cd \"$PLANTILLA_DIR\" && npm install)" >&2
  echo "       El acta en Markdown sí se generó: $ACTA_MD" >&2
  exit 1
fi
( cd "$PLANTILLA_DIR" && node render.mjs "$ACTA_MD" "$ACTA_PDF" )

echo ""
echo "✅ Listo:"
echo "   Transcripción : $TXT"
echo "   Acta (md)     : $ACTA_MD"
echo "   Acta (pdf)    : $ACTA_PDF"
echo ""
echo "   Revisa el acta antes de difundirla (transcripción automática)."
