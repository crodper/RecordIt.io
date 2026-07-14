"""Redacción del acta de reunión con Claude (paso opcional).

Dos backends, según cómo haya conectado recordIt (ver recordit.claude_auth):
- 'cli': usa el ejecutable `claude -p` del sistema (sin API key).
- 'api': usa la API de Anthropic con la API key obtenida del sistema.
Reutiliza el mismo prompt que el flujo interno (acta.sh).
"""
import json
import os
import subprocess
import urllib.error
import urllib.request

import anthropic

from . import claude_auth, glosario

MAX_TOKENS = 8192

COMANDO_LOGIN = "claude login"

URL_OPENAI = "https://api.openai.com/v1/chat/completions"

# Tope de espera de la llamada a OpenAI (segundos): guarda contra cuelgues, no
# un SLA ajustado — redactar un acta larga puede tardar.
TIMEOUT_OPENAI = 300

# Tope de tokens de salida para OpenAI: más holgado que el de Anthropic porque
# en los modelos de razonamiento (gpt-5) el cupo incluye los tokens de
# razonamiento, no solo el acta visible.
MAX_TOKENS_OPENAI = 16384

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
- Fichero de audio: grabaciones/{base}
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
7. Sección '## Acciones pendientes (action items)' como lista de tareas de Obsidian: una casilla por acción con el formato '- [ ] <acción>'. Si consta el responsable, añádelo tras la acción como ' — <Responsable>'; si consta una fecha límite concreta, añádela al final como ' 📅 AAAA-MM-DD' (emoji de fecha de Obsidian Tasks; úsalo solo si puedes expresar la fecha en formato AAAA-MM-DD, en caso contrario indica el plazo como texto). Omite las partes que no consten.
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


def _error_openai(exc) -> RuntimeError:
    """Traduce un fallo HTTP de OpenAI a un error en español accionable."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return RuntimeError(
                "La API key de OpenAI no es válida o ha caducado. "
                "Revísala en «⚙ Ajustes».")
        try:
            detalle = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            detalle = exc.reason
        return RuntimeError(
            f"OpenAI falló al redactar el acta (HTTP {exc.code}): {detalle}")
    return RuntimeError(
        f"No se pudo conectar con OpenAI: {getattr(exc, 'reason', exc)}")


def _redactar_openai(prompt: str, api_key: str, modelo: str) -> str:
    """Redacta el acta con la API de OpenAI (chat completions) vía urllib.

    Se usa la librería estándar para no añadir el SDK `openai` como dependencia.
    La familia gpt-5 usa `max_completion_tokens` (no `max_tokens`).
    """
    cuerpo = json.dumps({
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": MAX_TOKENS_OPENAI,
    }).encode("utf-8")
    req = urllib.request.Request(
        URL_OPENAI, data=cuerpo, method="POST",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_OPENAI) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:  # cubre también HTTPError
        raise _error_openai(exc) from exc
    opciones = datos.get("choices") or []
    if not opciones:
        raise RuntimeError(
            "OpenAI devolvió una respuesta vacía o inesperada al redactar el acta.")
    if opciones[0].get("finish_reason") == "length":
        raise RuntimeError(
            "OpenAI cortó el acta por longitud. Prueba con una transcripción más "
            "corta o con otro modelo.")
    contenido = (opciones[0].get("message") or {}).get("content")
    if not contenido:
        raise RuntimeError(
            "OpenAI devolvió una respuesta vacía o inesperada al redactar el acta.")
    return _limpiar_markdown(contenido)


def redactar_acta(transcripcion: str, *, fecha: str, base: str, proveedor: str = "claude",
                  metodo: str = "api", api_key: str = None,
                  modelo: str = "claude-opus-4-8", titulo=None) -> str:
    """Redacta el acta y devuelve el Markdown.

    proveedor: 'claude' (defecto) usa Claude (metodo 'cli' o 'api'); 'openai' usa
    la API de OpenAI con `api_key` y `modelo`.
    """
    prompt = construir_prompt(transcripcion, fecha=fecha, base=base, titulo=titulo)
    if proveedor == "openai":
        return _redactar_openai(prompt, api_key, modelo)
    if metodo == "cli":
        return _redactar_cli(prompt)
    return _redactar_api(prompt, api_key, modelo)
