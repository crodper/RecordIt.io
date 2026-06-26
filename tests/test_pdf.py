from recordit import pdf

ACTA = """---
title: "Acta — Prueba"
audiencia: "Equipo"
estado: "Acta interna"
tags: [acta, prueba]
---
# Acta — Prueba

| Fecha | Audio |
|---|---|
| 16 de junio | reunion.wav |

> **Nota:** sin diarización; dudoso marcado como *(dudoso)*.

## 1. Tema
- Punto **uno**.
- Punto dos *(dudoso)*.

## Decisiones tomadas
1. Decisión A.
2. Decisión B.
"""


def test_disponible_siempre():
    assert pdf.disponible() is True


def test_genera_pdf_valido(tmp_path):
    md = tmp_path / "acta.md"
    md.write_text(ACTA, encoding="utf-8")
    salida = tmp_path / "acta.pdf"
    pdf.generar(md, salida)
    datos = salida.read_bytes()
    assert datos.startswith(b"%PDF")
    assert len(datos) > 1000


def test_frontmatter_y_quita_h1_duplicado():
    fm, cuerpo = pdf._separar_frontmatter(ACTA)
    meta = pdf._parse_frontmatter(fm)
    assert meta["title"] == "Acta — Prueba"
    assert meta["estado"] == "Acta interna"
    # El cuerpo tras quitar el H1 ya no contiene el título como '# ...'.
    sin_h1 = pdf._quitar_primer_h1(cuerpo)
    assert "# Acta — Prueba" not in sin_h1


def test_inline_negrita_y_cursiva():
    assert "<b>uno</b>" in pdf._inline("Punto **uno**")
    assert "<i>dudoso</i>" in pdf._inline("texto *dudoso* fin")
