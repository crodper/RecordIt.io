# Construir `recordIt.exe` en Windows

Guía para generar el ejecutable de Windows de **recordIt** en una máquina Windows real.
Está escrita para que la siga **Claude Code** (o una persona) paso a paso.

> **Para Claude Code:** ejecuta los pasos en orden, en **PowerShell**, desde la raíz del
> repositorio (la carpeta que contiene `recordit.spec`). Tras cada paso, verifica la salida
> antes de seguir. No te saltes la verificación final. Todo el código y los mensajes del
> proyecto van en **español**.

## Por qué en Windows real

PyInstaller **no hace cross-compile** y el motor de transcripción (`ctranslate2`, que usa
`faster-whisper`) llama a funciones del runtime de C de Windows que **Wine no implementa**
(`ucrtbase.crealf`). Por eso el `.exe` **no** se puede generar desde Linux/Wine: hay que
construirlo en Windows. En Windows real `ctranslate2` funciona con normalidad.

## 0. Requisitos previos

Instala (una vez). Con `winget` desde PowerShell:

```powershell
winget install -e --id Python.Python.3.12     # Python 3.12 64-bit (recomendado)
winget install -e --id Git.Git                 # si vas a clonar el repo
# Opcional, solo si quieres además generar PDF de actas en esta máquina:
winget install -e --id OpenJS.NodeJS.LTS
```

- **Usa Python 3.12 de 64 bits.** Evita 3.13/3.14: puede que aún no haya ruedas (`wheels`)
  de `ctranslate2`/`numpy` para esas versiones en Windows.
- Cierra y reabre PowerShell tras instalar, para que `python` quede en el `PATH`.
- Comprueba: `python --version` debe decir `Python 3.12.x`.

## 1. Obtener el proyecto

Clónalo (o cópialo) y entra en la carpeta:

```powershell
git clone <URL-del-repositorio>
cd recordit
```

## 2. Entorno virtual e instalación de dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Esto instala `customtkinter`, `pillow`, `sounddevice`, `numpy`, `faster-whisper`
(arrastra `ctranslate2`), `anthropic`, `pytest` y `pyinstaller`.

> Si `Activate.ps1` falla por la política de ejecución:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y reintenta.

Verifica que las dependencias nativas cargan en Windows:

```powershell
python -c "import tkinter, customtkinter, PIL, sounddevice, ctranslate2, faster_whisper; print('deps OK')"
```

Debe imprimir `deps OK`. (Si `ctranslate2` se queja de `VCRUNTIME140.dll`, instala el
**Microsoft Visual C++ Redistributable x64**: `winget install -e --id Microsoft.VCRedist.2015+.x64`.)

## 3. Colocar ffmpeg (obligatorio)

El ejecutable empaqueta un `ffmpeg.exe` para preprocesar el audio. Descárgalo y déjalo en
`vendor\ffmpeg.exe`:

```powershell
New-Item -ItemType Directory -Force vendor | Out-Null
Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile "$env:TEMP\ffmpeg.zip"
Expand-Archive -Force "$env:TEMP\ffmpeg.zip" "$env:TEMP\ffmpeg"
Copy-Item (Get-ChildItem "$env:TEMP\ffmpeg" -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName "vendor\ffmpeg.exe"
Test-Path "vendor\ffmpeg.exe"   # debe ser True
```

(Alternativa: cualquier build estático de ffmpeg para Windows; solo se necesita `ffmpeg.exe`.)

## 4. Construir el ejecutable

El `recordit.spec` ya está preparado: detecta el SO y empaqueta `vendor\ffmpeg.exe`, los
temas de CustomTkinter, los iconos de `gui\assets\`, el icono de la app (`appicon.ico`) y los
`hiddenimports` necesarios (incluido `PIL._tkinter_finder`).

```powershell
.\build.ps1
```

(Equivale a `python -m PyInstaller --noconfirm --clean recordit.spec`.)

Resultado: **`dist\recordIt.exe`** (un solo fichero, ~150–200 MB).

## 5. Verificar

```powershell
.\dist\recordIt.exe
```

Comprobaciones:
- La ventana abre con el tema oscuro, el logo y los iconos; el título lleva el icono de la app.
- El desplegable lista micrófonos; **Grabar/Detener** mueve la onda y guarda un `.wav`.
- **Transcribir**: la **primera vez descarga el modelo `large-v3` (~3 GB)** a la caché del
  usuario (`%USERPROFILE%\.cache\huggingface`); necesita internet esa vez. Luego genera la
  transcripción.
- Los datos del usuario se crean en **`%USERPROFILE%\recordIt\`** (grabaciones y
  transcripciones/actas), no junto al `.exe`.
- **Generar acta**: requiere conexión con Claude — `claude` (Claude Code) instalado o la
  variable `ANTHROPIC_API_KEY`. El indicador de la cabecera lo refleja (⚙ Ajustes → Conectar).

> El **PDF** (`Generar PDF`) solo funciona si esta máquina tiene **Node** y se hizo
> `npm install` dentro de `pdf-template\`. No es necesario para el `.exe`.

## 6. Distribuir

Reparte el fichero **`dist\recordIt.exe`** (cópialo; no por git, pesa cientos de MB).
En la máquina destino:

- No requiere instalar Python ni ffmpeg (van dentro).
- 1ª transcripción: descarga el modelo (~3 GB, con internet).
- Para actas: que tenga Claude Code o `ANTHROPIC_API_KEY`.
- **SmartScreen**: al ser un `.exe` sin firmar, Windows puede avisar. *Más información →
  Ejecutar de todas formas*. (Para evitarlo habría que firmar el ejecutable con un
  certificado de código, fuera del alcance de esta guía.)

## Resolución de problemas

| Síntoma | Causa / solución |
|---|---|
| `pip` no encuentra rueda de `ctranslate2`/`numpy` | Estás en Python 3.13/3.14. Usa **Python 3.12 64-bit**. |
| `VCRUNTIME140.dll` no encontrado al importar `ctranslate2` | Instala **VC++ Redistributable x64** (`winget install Microsoft.VCRedist.2015+.x64`). |
| `Activate.ps1` bloqueado | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`. |
| El `.exe` tarda en abrir la 1ª vez | Normal: el one-file se autoextrae a `%TEMP%`. |
| Antivirus marca el `.exe` (falso positivo de PyInstaller) | Conocido en one-file. Añade excepción, o cambia a one-folder (ver nota). |
| Falla `Generar PDF` | Falta Node / `npm install` en `pdf-template\`. No afecta al resto. |
| Falla al transcribir con error de audio | Prueba otro micrófono del desplegable; la app ya cae a la frecuencia soportada. |

### Nota: one-folder en vez de one-file
Si el arranque one-file es lento o el antivirus molesta, cambia el final de `recordit.spec`
para producir una **carpeta** (arranque instantáneo) en lugar de un único `.exe`:

```python
exe = EXE(pyz, a.scripts, name="recordIt", console=False, icon=_icono, exclude_binaries=True)
coll = COLLECT(exe, a.binaries, a.datas, name="recordIt")
```

Entonces se distribuye la carpeta `dist\recordIt\` completa (con `recordIt.exe` dentro).

## Resumen rápido (TL;DR)

```powershell
winget install -e --id Python.Python.3.12
cd recordit
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# ffmpeg.exe -> vendor\ffmpeg.exe (ver paso 3)
.\build.ps1
.\dist\recordIt.exe   # verificar
```

## Conexión con Claude en el equipo del usuario

La app distribuida **no** usa la app de escritorio de Claude (no expone interfaz
a terceros) ni una API key. Para redactar actas, cada equipo necesita el **CLI
oficial de Claude Code** autenticado con la suscripción del usuario:

1. `npm install -g @anthropic-ai/claude-code` (requiere Node.js).
2. `claude login` — con la **misma cuenta** que la app de escritorio de Claude.

Tras eso, recordIt detecta `claude` automáticamente (queda en `%APPDATA%\npm`,
ya en el PATH). La propia app guía estos pasos en «Ajustes → Conectar con Claude».
