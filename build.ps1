# Construye recordIt.exe en Windows con PyInstaller.
# Requisitos previos: ejecutarlo desde la raíz del repo, con el venv ya creado y
# las dependencias instaladas (ver docs/BUILD-WINDOWS.md). Necesita vendor\ffmpeg.exe.
#
# Uso:  .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "vendor\ffmpeg.exe")) {
  Write-Error "Falta vendor\ffmpeg.exe. Descarga un ffmpeg estatico de Windows (ver docs\BUILD-WINDOWS.md)."
}

# Usa el Python del venv si existe; si no, el del PATH.
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -m PyInstaller --noconfirm --clean recordit.spec
Write-Host "Listo: dist\recordIt.exe"
