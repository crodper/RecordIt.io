# recordIt

Herramientas para **grabar reuniones presenciales**, **transcribirlas** con Whisper y
generar un **acta de reunión** a partir de la transcripción.

El flujo completo es:

```
grabar_reunion.py  →  grabaciones/reunion_*.wav  →  transcribir.py  →  transcripciones/<base>/transcripcion.txt  →  acta.md  →  acta.pdf
```

## Atajo: todo en un comando — `acta.sh`

Una vez tienes el `.wav`, `acta.sh` encadena **preprocesado → transcripción → redacción del acta → PDF** automáticamente:

```bash
./acta.sh grabaciones/reunion_2026-06-16_10-06-12.wav
# opcional: forzar un título de portada
./acta.sh grabaciones/reunion.wav "Acta — Revisión de fabricación ACS"
```

Genera en `transcripciones/<base>/` (una carpeta por grabación): `transcripcion.txt`, `transcripcion_timestamps.txt`, `acta.md` y `acta.pdf`.

- La redacción del acta la hace el **CLI de `claude`** (`claude -p`) leyendo la transcripción; debe estar instalado y autenticado.
- Si la transcripción no tiene contenido de reunión real, Claude **no inventará** un acta (mostrará un aviso). Revisa siempre el resultado antes de difundirlo.

Los apartados siguientes describen cada paso por separado por si quieres ejecutarlos a mano.

---

## GUI — `recordit_gui.py`

Interfaz gráfica para grabar, transcribir y (opcionalmente) generar el acta sin tocar
la terminal:

```bash
.venv/bin/python recordit_gui.py
```

- **Grabar/Detener** → guarda en `grabaciones/`.
- **Transcribir** → preprocesa y transcribe; la 1ª vez descarga el modelo `large-v3`.
- **Generar acta…** → opcional; recordIt conecta con Claude desde el sistema (CLI `claude`
  o `ANTHROPIC_API_KEY`). El indicador de la cabecera muestra si está conectado.
- **Generar PDF** → renderiza el acta a PDF en **Python puro** (reportlab); **no requiere
  Node** y funciona dentro del ejecutable. Encadena lo que falte (transcribir / generar acta)
  si aún no existe.
- En la app empaquetada, los datos viven en `~/recordIt/` (no junto al ejecutable).

### Ejecutable autocontenido

Se empaqueta con PyInstaller. El modelo no se empaqueta: se descarga en la 1ª ejecución. El
PDF del acta se genera en Python puro (reportlab), así que funciona dentro del ejecutable.

- **Linux:** coloca `vendor/ffmpeg` (estático) y ejecuta `./build.sh` (local) o
  `./build-linux.sh` (portable, ver abajo).
- **Windows:** se construye en una máquina Windows real (no desde Linux: Wine no puede con
  `ctranslate2`). Guía completa en **`docs/BUILD-WINDOWS.md`**; en resumen, `vendor\ffmpeg.exe`
  + `.\build.ps1` → `dist\recordIt.exe`.

> **Linux portable:** construye con `./build-linux.sh`, que usa Docker (`Dockerfile.linux`)
> para compilar sobre una glibc antigua (Debian bullseye, glibc 2.31). Construir en un
> equipo con glibc nueva genera un binario que falla en otros con «GLIBC_x.y not found»
> (glibc solo es compatible hacia adelante). Salida: `dist-portable/recordIt`.

---

## Requisitos

- **Python 3.9+**
- **ffmpeg** (preprocesado de audio antes de transcribir)
- PortAudio (necesario para grabar)

Instalación de ffmpeg y PortAudio según el sistema:

| Sistema | ffmpeg | PortAudio |
|---|---|---|
| **Linux (Debian/Ubuntu)** | `sudo apt install ffmpeg` | `sudo apt install libportaudio2` |
| **macOS (Homebrew)** | `brew install ffmpeg` | `brew install portaudio` |
| **Windows** | `winget install ffmpeg` (o [ffmpeg.org](https://ffmpeg.org/download.html)) | incluido con la rueda de `sounddevice` (pip) |

Además, para generar el acta automáticamente con `acta.sh` hace falta el **CLI de `claude`**
(Claude Code) instalado y autenticado, y **Node 18+** para la plantilla PDF.

### Instalación

```bash
# 1. Dependencias Python (grabación y transcripción)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Dependencias de la plantilla PDF (descarga Chromium la primera vez)
cd pdf-template && npm install && cd ..
```

`requirements.txt` incluye:
- `sounddevice`, `numpy` — para grabar.
- `faster-whisper` — para transcribir.

> **El modelo de Whisper NO está en el repo.** `faster-whisper` descarga `large-v3` (~3 GB)
> automáticamente a `~/.cache/huggingface` la primera vez que transcribes. Necesita conexión
> a internet esa primera vez.

> **La plantilla PDF (`pdf-template/`) va incluida en el repo**, pero su `node_modules/` no:
> por eso el `npm install` del paso 2. Los colores, fuentes, texto del pie y logo se
> configuran en `pdf-template/brand.json` (y `pdf-template/assets/` para el logo).

---

## 1. Grabar una reunión — `grabar_reunion.py`

Graba audio del micrófono a un `.wav`, escribiendo al disco en tiempo real (si el
programa se corta, no pierdes lo grabado). Incluye **ganancia automática (AGC)** para
subir el volumen de micrófonos flojos sin saturar, y un **medidor de nivel (VU meter)**
en tiempo real.

```bash
# Graba hasta Ctrl+C (AGC activado, nombre con fecha/hora automático)
python grabar_reunion.py

# Listar micrófonos disponibles
python grabar_reunion.py --listar

# Elegir micrófono concreto (índice de --listar)
python grabar_reunion.py --dispositivo 24

# Nombre de salida concreto
python grabar_reunion.py -o reunion.wav

# Limitar duración (segundos). Ej.: como mucho 1 hora
python grabar_reunion.py -d 3600

# Ganancia fija x3 (en vez de AGC) o sin ganancia
python grabar_reunion.py --ganancia 3
python grabar_reunion.py --ganancia off
```

**Opciones principales:**

| Opción | Por defecto | Descripción |
|---|---|---|
| `-o, --salida` | `grabaciones/reunion_<fecha>_<hora>.wav` | Fichero de salida |
| `-r, --frecuencia` | `44100` | Frecuencia de muestreo (Hz) |
| `-c, --canales` | `1` (mono) | 1=mono (voz), 2=estéreo |
| `-d, --duracion` | ilimitada | Duración máxima (s) |
| `--dispositivo` | sistema | Índice del micrófono (`--listar`) |
| `-g, --ganancia` | `auto` | `auto` (AGC), un número (fija) u `off` |
| `--listar` | — | Lista micrófonos y sale |

El VU meter avisa con `SATURA!` si el pico supera −3 dB y con `(muy bajo)` si baja de −45 dB.

---

## 2. Transcribir — `transcribir.py`

Transcribe un `.wav` con **faster-whisper (modelo `large-v3`, el más preciso)** en CPU.
Usa **VAD** para saltar silencios y `condition_on_previous_text=False` para evitar los
bucles de alucinación típicos en audio de sala con ruido.

> **Recomendado:** preprocesar el audio con ffmpeg antes de transcribir mejora mucho la
> calidad en grabaciones de sala (reduce ruido, normaliza el volumen y baja a 16 kHz mono,
> que es lo que espera Whisper):
>
> ```bash
> ffmpeg -y -i reunion.wav \
>   -af "highpass=f=80,lowpass=f=8000,afftdn=nf=-25,dynaudnorm=f=150:g=15" \
>   -ar 16000 -ac 1 -c:a pcm_s16le reunion_clean_16k.wav
> ```

Transcripción:

```bash
# python transcribir.py <audio_entrada> <txt_salida>
python transcribir.py grabaciones/reunion_clean_16k.wav transcripciones/reunion/transcripcion.txt
```

Genera dos ficheros:
- `transcripciones/reunion/transcripcion.txt` — texto plano (una línea por segmento).
- `transcripciones/reunion/transcripcion_timestamps.txt` — lo mismo con marcas de tiempo `[HH:MM:SS -> HH:MM:SS]`.

**Notas:**
- La primera ejecución descarga el modelo `large-v3` (~3 GB) a `~/.cache/huggingface`.
- En CPU, transcribir ~30 min de audio tarda un buen rato; conviene lanzarlo en segundo plano.
- El idioma está fijado a español (`language="es"`) dentro del script.

### Limitaciones

- El audio es de **un solo canal, sin separación de interlocutores (sin diarización)**:
  la transcripción no indica *quién* dice cada frase. Para diarización se necesitaría otra
  herramienta (p. ej. `whisperX` con `pyannote`).
- En tramos de audio de baja calidad pueden aparecer errores o palabras inventadas; conviene
  revisar la transcripción.

---

## 3. Generar el acta de reunión

A partir de la transcripción se redacta un acta en Markdown (`transcripciones/<base>/acta.md`)
con: resumen por temas, decisiones tomadas, acciones pendientes (responsable/plazo) y calendario.
Revisa siempre el acta contra tu memoria de la reunión antes de difundirla, especialmente los
puntos marcados como dudosos.

---

## Escuchar una grabación

```bash
aplay archivo.wav
```

---

## Estructura del proyecto

```
recordIt/
├── acta.sh                  # Flujo completo: wav → md + pdf del acta
├── grabar_reunion.py        # Grabador con AGC y VU meter
├── transcribir.py           # Transcriptor (faster-whisper large-v3)
├── requirements.txt
├── grabaciones/             # Grabaciones .wav (no versionar)
│   └── reunion_*.wav
└── transcripciones/         # Una carpeta por grabación
    └── <base>/
        ├── transcripcion.txt             # Transcripción en texto plano
        ├── transcripcion_timestamps.txt  # Transcripción con marcas de tiempo
        ├── acta.md                       # Acta de reunión (Markdown)
        ├── acta.pdf                      # Acta de reunión (PDF)
        └── clean_16k.wav                 # Audio preprocesado (intermedio)
```
