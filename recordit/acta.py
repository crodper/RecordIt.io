"""Redacción del acta de reunión con Claude (paso opcional).

Dos backends, según cómo haya conectado recordIt (ver recordit.claude_auth):
- 'cli': usa el ejecutable `claude -p` del sistema (sin API key).
- 'api': usa la API de Anthropic con la API key obtenida del sistema.
Reutiliza el mismo prompt que el flujo interno (acta.sh).
"""
import os
import subprocess

import anthropic

from . import claude_auth, glosario

MAX_TOKENS = 8192

COMANDO_LOGIN = "claude login"

# Subcadenas del stderr/stdout del CLI que delatan falta de sesión iniciada.
_PISTAS_LOGIN = ("login", "log in", "authenticat", "not logged in",
                 "unauthorized", "invalid api key")


def _error_legible(exc: subprocess.CalledProcessError) -> RuntimeError:
    """Traduce un fallo del CLI `claude` a un error en español accionable."""
    salida = ((exc.stderr or "") + " " + (exc.output or "")).strip()
    bajo = salida.lower()
    if any(pista in bajo for pista in _PISTAS_LOGIN):
        return RuntimeError(
            "Claude Code está instalado pero sin sesión iniciada. Abre una "
            f"terminal, ejecuta «{COMANDO_LOGIN}» (con la misma cuenta que tu "
            "app de Claude) y vuelve a intentarlo.")
    detalle = salida or f"código de salida {exc.returncode}"
    return RuntimeError(f"Claude Code falló al redactar el acta: {detalle}")


def construir_prompt(transcripcion: str, *, fecha: str, base: str, titulo=None) -> str:
    titulo_yaml = titulo or "Acta de reunión — <pon aquí un título corto y descriptivo del tema principal>"
    bloque_glosario = glosario.bloque_prompt()
    seccion_glosario = f"\n{bloque_glosario}\n" if bloque_glosario else ""
    return f"""Eres un asistente que redacta actas de reunión en español a partir de una transcripción automática.

Datos de esta reunión:
- Fecha: {fecha}
- Fichero de audio: grabaciones/{base}.wav
- Transcripción: transcripciones/{base}/transcripcion.txt (Whisper large-v3)

A continuación, tras la línea '=== TRANSCRIPCIÓN ===', tienes la transcripción completa.

Redacta un ACTA DE REUNIÓN en Markdown siguiendo EXACTAMENTE estas reglas:
1. Empieza con un front-matter YAML con estos campos (sin comillas extra):
---
title: "{titulo_yaml}"
audiencia: "<a quién va dirigida, p. ej. Equipo de producto / desarrollo>"
estado: "Acta interna — revisar antes de difundir"
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
{seccion_glosario}
=== TRANSCRIPCIÓN ===
{transcripcion}"""


def _limpiar_markdown(texto: str) -> str:
    """Quita un envoltorio ```markdown ... ``` si el modelo lo añadió."""
    lineas = texto.strip().splitlines()
    if lineas and lineas[0].startswith("```"):
        lineas = lineas[1:]
    if lineas and lineas[-1].strip() == "```":
        lineas = lineas[:-1]
    return "\n".join(lineas).strip()


def _redactar_api(prompt: str, api_key: str, modelo: str) -> str:
    cliente = anthropic.Anthropic(api_key=api_key)
    mensaje = cliente.messages.create(
        model=modelo, max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}])
    return _limpiar_markdown(mensaje.content[0].text)


def _redactar_cli(prompt: str) -> str:
    """Usa el CLI `claude -p` del sistema (Claude Code ya autenticado).

    El prompt va por stdin (no por argumento) para no chocar con el límite de
    longitud de la línea de comandos en Windows. Los .cmd/.bat se ejecutan vía
    cmd.exe; los .exe directamente.
    """
    exe = claude_auth.ruta_cli() or "claude"
    cmd = [exe, "-p"]
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c", exe, "-p"]
    try:
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                             check=True, encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        raise _error_legible(exc) from exc
    return _limpiar_markdown(res.stdout)


def redactar_acta(transcripcion: str, *, fecha: str, base: str, metodo: str = "api",
                  api_key: str = None, modelo: str = "claude-opus-4-8", titulo=None) -> str:
    """Redacta el acta y devuelve el Markdown.

    metodo: 'cli' usa el ejecutable `claude`; 'api' usa la API con `api_key`.
    """
    prompt = construir_prompt(transcripcion, fecha=fecha, base=base, titulo=titulo)
    if metodo == "cli":
        return _redactar_cli(prompt)
    return _redactar_api(prompt, api_key, modelo)
