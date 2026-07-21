# CLAUDE.md — recordIt

Guía para trabajar en este proyecto. Léela antes de modificar código o documentación.

## Qué es

Herramientas de línea de comandos para **grabar reuniones presenciales**, **transcribirlas**
con Whisper y generar **actas de reunión**. No es una librería ni un servicio: son scripts
sueltos que se ejecutan a mano.

Flujo: `grabar_reunion.py → grabaciones/reunion_*.wav → transcribir.py → transcripciones/<base>/transcripcion.txt → transcripciones/<base>/acta.md`

Para **reuniones online** hay un modo (interruptor en la GUI, flag `--reunion-online`
en la CLI) que además del micrófono captura el **audio de salida del sistema**
(fuentes `*.monitor` en Linux, WASAPI loopback en Windows) y lo mezcla en el mismo
mono. La salida se auto-detecta; si no la hay, graba solo micro.

## Estructura

```
acta.sh             # Flujo completo en un comando: wav → md + pdf del acta
grabar_reunion.py   # Grabador: micrófono → grabaciones/*.wav, con AGC y VU meter
transcribir.py      # Transcriptor: .wav → .txt usando faster-whisper large-v3
requirements.txt    # sounddevice, numpy (grabar) + faster-whisper (transcribir)
grabaciones/        # Grabaciones .wav (no versionar; son grandes)
transcripciones/    # Una carpeta por grabación; dentro, salidas con nombres cortos
.venv/              # Entorno virtual (no versionar)
recordit/           # Lógica núcleo reutilizable (audio, transcripcion, acta, config, rutas)
gui/                # GUI Tkinter (app.py)
recordit_gui.py     # Lanzador de la GUI
recordit.spec       # Receta PyInstaller (build por SO)
```

Cada grabación tiene su carpeta en `transcripciones/<base>/` con nombres cortos
(la carpeta ya identifica la reunión):

```
transcripciones/<base>/
  transcripcion.txt             # transcripción en texto plano
  transcripcion_timestamps.txt  # transcripción con marcas de tiempo
  acta.md                       # acta en Markdown (con front-matter)
  acta.pdf                      # acta en PDF
  clean_16k.wav                 # audio preprocesado (intermedio)
```

**`acta.sh <audio.wav>` es el flujo estándar**: preprocesa con ffmpeg → transcribe con
`transcribir.py` → redacta el acta con `claude -p` → renderiza el PDF con la plantilla
**vendorizada en `pdf-template/`** (override con la variable `PDF_TEMPLATE_DIR`). El
acta `.md` lleva front-matter YAML (`title`, `audiencia`, `estado`, `tags`) que la plantilla
necesita. La plantilla requiere `npm install` una vez dentro de `pdf-template/`.

## Entorno

- Usa siempre el venv: `source .venv/bin/activate` (o `.venv/bin/python ...`).
- Solo CPU disponible (sin GPU). Tenerlo en cuenta al elegir modelos/tiempos.
- `ffmpeg` debe estar en el PATH para el preprocesado de audio.

## Convenciones

- **Idioma:** todo el código, comentarios, docstrings y mensajes al usuario en **español**.
- **Nomenclatura:** funciones y variables en español (p. ej. `grabar`, `ganancia`,
  `dispositivo`), siguiendo el estilo ya presente en `grabar_reunion.py`.
- **Sin dependencias nuevas** salvo necesidad real; mantener `requirements.txt` al día si se añaden.
- **CLI con `argparse`**, valores por defecto sensatos y `--help` claro (ver `grabar_reunion.py`).
- **Escritura incremental al disco**: el grabador escribe en tiempo real para no perder datos
  si se corta; mantener esa propiedad en cambios.
- Audio para transcribir: **16 kHz mono**. Preprocesar con ffmpeg (denoise + normalize) antes
  de pasar por Whisper mejora mucho la calidad en audio de sala.

## Decisiones tomadas (y por qué)

- **Modelo de transcripción: `large-v3`** vía `faster-whisper` (no `openai-whisper`).
  Misma precisión que large-v3 pero viable en CPU. El modelo `medium` daba transcripciones
  inservibles (bucles de alucinación) con audio de sala ruidoso.
- **`vad_filter=True`** y **`condition_on_previous_text=False`** para evitar bucles de
  repetición/alucinación. No quitar sin un motivo claro.
- **No hay diarización** (no se identifica quién habla). Si se necesita, valorar `whisperX` +
  `pyannote`, no improvisar.
- **GUI con CustomTkinter + PyInstaller**: un solo runtime de Python. Empaquetado **Linux**
  con `build.sh` (local) / `build-linux.sh` (portable vía Docker/AppImage). El `.exe` de
  **Windows** se construye **en Windows real** (no desde Linux: Wine no implementa
  `ucrtbase.crealf` que usa `ctranslate2`); guía en `docs/BUILD-WINDOWS.md` (`build.ps1`).
  Se usa **CustomTkinter** (Tkinter por debajo) por aspecto moderno
  (esquinas redondeadas, modo claro/oscuro, acento de color); el `recordit.spec` debe
  empaquetar sus temas con `collect_all("customtkinter")`. La lógica vive en `recordit/`
  (la GUI la importa, nunca lanza subprocesos de Python). El acta en la app distribuida usa
  la **API de Anthropic** (no el CLI `claude`) y es opcional; el PDF de la GUI se genera en
  Python puro (`recordit/pdf.py`, reportlab), sin Node (`acta.sh` sigue usando la plantilla
  Puppeteer para el flujo de línea de comandos).
- **Selector de proveedor de IA en la GUI**: el acta admite **dos proveedores**, Claude
  (por defecto) u OpenAI; OpenAI se autentica pegando la API key en «⚙ Ajustes» y se llama
  con `urllib` de la librería estándar (sin SDK `openai` ni dependencia nueva), con modelos
  `gpt-5`/`gpt-5-mini`. `acta.sh` (flujo interno) sigue usando únicamente el CLI de Claude.

## Al generar un acta

- El audio es mono sin diarización: **no atribuir frases a personas concretas**.
- Marcar como *(dudoso)* los tramos de baja calidad del audio.
- Estructura del acta: resumen por temas → decisiones → acciones (responsable/plazo) → calendario.
- Avisar al usuario de que revise el acta antes de difundirla.

## Qué NO hacer

- No versionar `.venv/`, `*.wav` ni modelos descargados (`~/.cache/huggingface`).
- No cambiar el idioma de salida de la transcripción sin pedirlo (está fijado a `es`).
- No inventar contenido en el acta que no esté en la transcripción.
