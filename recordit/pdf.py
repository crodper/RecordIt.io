"""Genera el PDF del acta en Python puro (reportlab), sin Node ni Chromium.

Parsea el acta en Markdown (con front-matter YAML simple) y la maqueta con la
paleta de pdf-template/brand.json. No tiene dependencias nativas, así que
empaqueta limpio en el .exe/AppImage y funciona en cualquier máquina. No
reproduce pixel a pixel la plantilla Puppeteer, pero mantiene la identidad
visual (cabecera, colores, secciones, tablas, nota y pie).
"""
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, Image, ListFlowable,
                                ListItem, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

# --- Paleta (espejo de pdf-template/brand.json) -----------------------------
NAVY = colors.HexColor("#243447")
TEAL = colors.HexColor("#3a7ca5")
TEXTO = colors.HexColor("#1f2a33")
MUTED = colors.HexColor("#5b6b76")
REGLA = colors.HexColor("#dbe3e8")
FILA_ALT = colors.HexColor("#f4f8fa")
NOTA_BG = colors.HexColor("#eef4f8")
PIE = "RecordIt · Documento interno"


def disponible() -> bool:
    """Siempre disponible: reportlab va empaquetado, no hace falta Node."""
    return True


# --- estilos ----------------------------------------------------------------
def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=10, leading=14,
                          textColor=TEXTO)
    return {
        "base": base,
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold",
                             fontSize=20, leading=24, textColor=NAVY, spaceAfter=2),
        "meta": ParagraphStyle("meta", parent=base, fontSize=9, textColor=MUTED, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold",
                             fontSize=13, leading=17, textColor=TEAL,
                             spaceBefore=12, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold",
                             fontSize=11, leading=15, textColor=NAVY,
                             spaceBefore=8, spaceAfter=2),
        "nota": ParagraphStyle("nota", parent=base, fontSize=9.5, leading=13,
                              textColor=NAVY, leftIndent=8, rightIndent=8),
        "celda": ParagraphStyle("celda", parent=base, fontSize=9, leading=12),
        "celda_h": ParagraphStyle("celda_h", parent=base, fontSize=9, leading=12,
                                 fontName="Helvetica-Bold", textColor=colors.white),
    }


# --- parseo del markdown ----------------------------------------------------
def _separar_frontmatter(texto):
    if texto.lstrip().startswith("---"):
        partes = texto.split("---", 2)
        if len(partes) >= 3:
            return partes[1], partes[2]
    return "", texto


def _parse_frontmatter(fm):
    datos = {}
    for linea in fm.splitlines():
        m = re.match(r"\s*(\w+)\s*:\s*(.*)", linea)
        if m:
            datos[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return datos


def _quitar_primer_h1(cuerpo):
    """Elimina el primer encabezado nivel 1 (# ...) del cuerpo."""
    lineas = cuerpo.splitlines()
    for idx, ln in enumerate(lineas):
        if re.match(r"^#\s+\S", ln.strip()):
            del lineas[idx]
            break
    return "\n".join(lineas)


def _inline(texto):
    """Markdown inline -> markup mínimo de reportlab Paragraph."""
    s = html.escape(texto, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', s)
    s = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*", r"<i>\1</i>", s)
    return s


def _es_fila_tabla(linea):
    return linea.strip().startswith("|")


def _celdas(linea):
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def _construir_flowables(cuerpo, est):
    flow = []
    lineas = cuerpo.splitlines()
    i, n = 0, len(lineas)
    while i < n:
        linea = lineas[i]
        s = linea.strip()

        if not s:
            i += 1
            continue

        # Encabezados
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            nivel = len(m.group(1))
            estilo = {1: "h1", 2: "h2", 3: "h3"}[nivel]
            flow.append(Paragraph(_inline(m.group(2)), est[estilo]))
            i += 1
            continue

        # Tabla GFM
        if _es_fila_tabla(s):
            filas = []
            while i < n and _es_fila_tabla(lineas[i]):
                filas.append(_celdas(lineas[i]))
                i += 1
            flow.append(_tabla(filas, est))
            continue

        # Nota / cita
        if s.startswith(">"):
            citas = []
            while i < n and lineas[i].strip().startswith(">"):
                citas.append(lineas[i].strip()[1:].strip())
                i += 1
            flow.append(_nota(" ".join(citas), est))
            continue

        # Listas (con viñeta o numeradas)
        if re.match(r"^[-*]\s+", s) or re.match(r"^\d+[.)]\s+", s):
            items, ordenada = [], bool(re.match(r"^\d+[.)]\s+", s))
            while i < n:
                t = lineas[i].strip()
                m2 = re.match(r"^(?:[-*]|\d+[.)])\s+(.*)", t)
                if not m2:
                    break
                items.append(ListItem(Paragraph(_inline(m2.group(1)), est["base"]),
                                      leftIndent=14))
                i += 1
            flow.append(ListFlowable(items, bulletType="1" if ordenada else "bullet",
                                     bulletColor=TEAL, start="1" if ordenada else None))
            continue

        # Párrafo (junta líneas hasta blanco/estructura)
        parr = [s]
        i += 1
        while i < n:
            t = lineas[i].strip()
            if (not t or re.match(r"^#{1,3}\s", t) or _es_fila_tabla(t)
                    or t.startswith(">") or re.match(r"^[-*]\s+", t)
                    or re.match(r"^\d+[.)]\s+", t)):
                break
            parr.append(t)
            i += 1
        flow.append(Paragraph(_inline(" ".join(parr)), est["base"]))
    return flow


def _tabla(filas, est):
    if not filas:
        return Spacer(1, 0)
    # GFM: 2ª fila es el separador ---|--- ; se descarta si lo es.
    cuerpo = filas[:]
    if len(cuerpo) >= 2 and all(set(c) <= set("-: ") and "-" in c for c in cuerpo[1]):
        cabecera, datos = cuerpo[0], cuerpo[2:]
        tiene_cabecera = True
    else:
        cabecera, datos, tiene_cabecera = cuerpo[0], cuerpo[1:], False

    data = []
    if tiene_cabecera:
        data.append([Paragraph(_inline(c), est["celda_h"]) for c in cabecera])
    else:
        data.append([Paragraph(_inline(c), est["celda"]) for c in cabecera])
    for fila in datos:
        data.append([Paragraph(_inline(c), est["celda"]) for c in fila])

    t = Table(data, hAlign="LEFT", repeatRows=1 if tiene_cabecera else 0)
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, REGLA),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if tiene_cabecera:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), NAVY),
                   ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY)]
        for r in range(2, len(data), 2):
            estilo.append(("BACKGROUND", (0, r), (-1, r), FILA_ALT))
    t.setStyle(TableStyle(estilo))
    return t


def _nota(texto, est):
    parr = Paragraph(_inline(texto), est["nota"])
    t = Table([[parr]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NOTA_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


# --- documento (cabecera + pie) ---------------------------------------------
def _pie_y_cabecera(canvas, doc):
    canvas.saveState()
    ancho, alto = A4
    # Cabecera: banda fina de color.
    canvas.setFillColor(TEAL)
    canvas.rect(0, alto - 6 * mm, ancho, 6 * mm, fill=1, stroke=0)
    # Pie: texto + número de página.
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 12 * mm, PIE)
    canvas.drawRightString(ancho - 18 * mm, 12 * mm, f"Página {doc.page}")
    canvas.setStrokeColor(REGLA)
    canvas.line(18 * mm, 16 * mm, ancho - 18 * mm, 16 * mm)
    canvas.restoreState()


def generar(md, pdf) -> None:
    """Renderiza el acta en Markdown (`md`) a `pdf`."""
    texto = Path(md).read_text(encoding="utf-8")
    fm, cuerpo = _separar_frontmatter(texto)
    meta = _parse_frontmatter(fm)
    est = _estilos()

    flow = []
    titulo = meta.get("title")
    if titulo:
        flow.append(Paragraph(_inline(titulo), est["h1"]))
        sub = " · ".join(x for x in (meta.get("audiencia"), meta.get("estado")) if x)
        if sub:
            flow.append(Paragraph(_inline(sub), est["meta"]))
        cuerpo = _quitar_primer_h1(cuerpo)  # el acta repite el título como # H1
    flow += _construir_flowables(cuerpo, est)

    doc = BaseDocTemplate(
        str(pdf), pagesize=A4, title=titulo or "Acta de reunión",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=24 * mm, bottomMargin=22 * mm)
    marco = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="cuerpo")
    doc.addPageTemplates([PageTemplate(id="acta", frames=[marco],
                                       onPage=_pie_y_cabecera)])
    doc.build(flow)
