# Construir `recordIt.app` en macOS

Guía para generar la app de macOS de **recordIt** en un Mac real (Apple Silicon).
Está escrita para que la siga **Claude Code** (o una persona) paso a paso.

> **Para Claude Code:** ejecuta los pasos en orden, desde la raíz del repositorio
> (la carpeta que contiene `recordit.spec`). Tras cada paso, verifica la salida antes
> de seguir. No te saltes la verificación final. Todo el código y los mensajes del
> proyecto van en **español**.

> **Estado:** el empaquetado se ha escrito y revisado, pero **todavía no se ha
> ejecutado en un Mac**. Si algo de esta guía no cuadra con la realidad, corrige la
> guía además del código.

## Por qué en macOS real

PyInstaller **no hace cross-compile**: el `.app` se construye en macOS. Además, en
Apple Silicon los binarios necesitan al menos una **firma ad-hoc** para arrancar, y
esa la pone PyInstaller durante el build — no hay forma de producirla desde Linux.

## 0. Requisitos previos

- **macOS 14 (Sonoma) o superior** en Apple Silicon (arm64). El wheel de
  `onnxruntime` (la VAD de Whisper) solo se publica para arm64 y pide macOS 14+.
  Para un Mac Intel habría que fijar `onnxruntime<=1.23` en `requirements.txt`.
- **Python 3.12 de 64 bits.** Usa el instalador de [python.org](https://www.python.org/downloads/macos/)
  (trae Tcl/Tk 8.6, que necesita Tkinter) o Homebrew:

```bash
brew install python@3.12 python-tk@3.12
```

> No uses el Python del sistema: su Tcl/Tk es antiguo y la GUI se ve mal o no abre.

Comprueba:

```bash
python3.12 --version          # Python 3.12.x
python3.12 -c "import tkinter; print(tkinter.TkVersion)"   # 8.6
```

## 1. Obtener el proyecto

```bash
git clone <URL-del-repositorio>
cd recordit
```

## 2. Entorno virtual e instalación de dependencias

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verifica que las dependencias nativas cargan:

```bash
python -c "import tkinter, customtkinter, PIL, sounddevice, ctranslate2, faster_whisper; print('deps OK')"
```

Debe imprimir `deps OK`. A diferencia de Linux, **no hace falta instalar PortAudio
aparte**: el wheel de `sounddevice` trae `libportaudio.dylib`.

## 3. Colocar ffmpeg (obligatorio)

La app empaqueta un `ffmpeg` para preprocesar el audio. Tiene que ser un binario
**estático arm64**: el de Homebrew enlaza contra `/opt/homebrew/lib` y no funcionaría
en un Mac sin Homebrew.

```bash
mkdir -p vendor
curl -fsSL -o /tmp/ffmpeg.zip https://www.osxexperts.net/ffmpeg711arm.zip
unzip -o -j /tmp/ffmpeg.zip ffmpeg -d vendor
chmod +x vendor/ffmpeg
file vendor/ffmpeg          # debe decir: Mach-O 64-bit executable arm64
otool -L vendor/ffmpeg      # solo librerías de /usr/lib y /System
```

> Si el `.app` acaba sin `ffmpeg` empaquetado, `recordit/preproceso.py` cae a las
> rutas de Homebrew (`/opt/homebrew/bin/ffmpeg`, `/usr/local/bin/ffmpeg`), porque una
> app lanzada desde Finder no hereda el `PATH` del shell. Es una red de seguridad para
> builds locales, no para distribuir.

## 4. Construir la app

```bash
./build-macos.sh
```

(Equivale a `python -m PyInstaller --noconfirm --clean recordit.spec` más el
`ditto` que comprime el resultado.)

Resultado:
- **`dist/recordIt.app`** — la app (carpeta, ~1 GB).
- **`dist/recordIt-macos-arm64.zip`** — la app comprimida con `ditto`, lista para
  distribuir. Se usa `ditto` y no `zip` para conservar los enlaces internos del
  bundle y la firma ad-hoc.

El `recordit.spec` detecta macOS y produce un `.app` con `Info.plist` (en Linux y
Windows sigue produciendo un binario one-file). El `Info.plist` declara
`NSMicrophoneUsageDescription`: sin ese texto macOS **deniega el micrófono en
silencio** y la grabación sale muda.

## 5. Verificar

```bash
open dist/recordIt.app
```

Comprobaciones:
- La ventana abre con el tema oscuro, el logo y los iconos.
- La **primera** grabación hace que macOS pida permiso de micrófono. Acéptalo. Si lo
  deniegas: Ajustes del Sistema → Privacidad y seguridad → Micrófono.
- El desplegable lista micrófonos; **Grabar/Detener** mueve la onda y guarda un `.wav`.
- **Transcribir**: la primera vez descarga el modelo `large-v3` (~3 GB) a
  `~/.cache/huggingface`; necesita internet esa vez.
- Los datos del usuario se crean en **`~/recordIt/`**, no dentro del `.app`.
- **Generar acta**: requiere conexión con Claude (ver la última sección).

## 6. Audio del sistema (reunión online)

macOS **no** tiene loopback nativo, así que el interruptor «Reunión online» necesita
un dispositivo virtual. recordIt detecta **BlackHole**:

```bash
brew install --cask blackhole-2ch
```

Después hay que enviarle la salida del sistema, porque BlackHole no la duplica solo:

1. Abre **Configuración de Audio MIDI** (`/Applications/Utilities`).
2. **+** → *Crear dispositivo de salida múltiple*.
3. Marca tus altavoces/auriculares **y** «BlackHole 2ch».
4. Selecciona ese dispositivo múltiple como salida del sistema.

Con eso, recordIt encuentra la entrada de BlackHole y la mezcla con el micrófono. Sin
BlackHole, el aviso de la GUI lo dice y la grabación sigue con solo micrófono.

## 7. Distribuir

Reparte **`dist/recordIt-macos-arm64.zip`** (cópialo; no por git, pesa cientos de MB).
En el Mac destino:

- No requiere instalar Python ni ffmpeg (van dentro).
- 1ª transcripción: descarga el modelo (~3 GB, con internet).
- **Gatekeeper**: la app no está notarizada (haría falta un Developer ID de pago), así
  que al abrirla descargada macOS avisa de que no se puede verificar. La primera vez:
  **clic derecho sobre la app → Abrir → Abrir**. Alternativa por terminal:
  `xattr -dr com.apple.quarantine /ruta/recordIt.app`.

## Resolución de problemas

| Síntoma | Causa / solución |
|---|---|
| `pip` no encuentra rueda de `onnxruntime` | Mac Intel o macOS < 14. Fija `onnxruntime<=1.23` o usa Apple Silicon con macOS 14+. |
| La GUI abre fea o no abre | Python del sistema (Tcl/Tk antiguo). Usa el de python.org o `brew install python-tk@3.12`. |
| La grabación sale muda | Permiso de micrófono denegado: Ajustes del Sistema → Privacidad y seguridad → Micrófono. |
| «No se puede abrir porque Apple no puede comprobar…» | Gatekeeper: clic derecho → Abrir (ver paso 7). |
| «Reunión online» avisa de «solo micrófono» | Falta BlackHole o la salida no va a un dispositivo múltiple (ver paso 6). |
| `No se encontró ffmpeg` al preprocesar | Faltó el paso 3, o el `vendor/ffmpeg` no es arm64. |

## Resumen rápido (TL;DR)

```bash
brew install python@3.12 python-tk@3.12
cd recordit
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# ffmpeg estático arm64 -> vendor/ffmpeg (ver paso 3)
./build-macos.sh
open dist/recordIt.app   # verificar
```

## Conexión con Claude en el Mac del usuario

Igual que en Windows, la app usa el **CLI oficial de Claude Code** autenticado con la
suscripción del usuario (ni la app de escritorio ni una API key):

1. «⚙ Ajustes» → «Conectar con Claude» → **«Instalar Claude Code»**: recordIt ejecuta
   el instalador nativo oficial (`curl -fsSL https://claude.ai/install.sh | bash`), que
   **no requiere Node.js** ni permisos de administrador.
2. Al terminar, recordIt abre **Terminal.app** con `claude auth login` (vía
   AppleScript): inicia sesión ahí con la misma cuenta que la app de escritorio.
3. recordIt detecta la sesión solo.

El instalador nativo deja el CLI en `~/.local/bin/claude`; recordIt también mira
`/opt/homebrew/bin/claude` y `/usr/local/bin/claude`, porque una app lanzada desde
Finder no hereda el `PATH` del shell.

Guía oficial: <https://code.claude.com/docs/es/setup#native-install-recommended>
