# Plantilla PDF

Convierte cualquier `.md` (con front-matter) en un PDF con **portada, cabecera y pie**.

## Uso

```bash
cd pdf-template
npm install          # solo la primera vez (descarga Chromium)
node render.mjs "../mi-documento.md"
```

El PDF se crea junto al `.md` de origen. Para elegir nombre de salida:

```bash
node render.mjs "entrada.md" "salida.pdf"
```

## Qué lee de cada documento

Del **front-matter** YAML del `.md`:

```yaml
---
title: "Título que aparece en la portada y la cabecera"
audiencia: "Subtítulo / a quién va dirigido"
estado: "Borrador"
tags: [reunion, acta]
---
```

`title` → portada + cabecera · `audiencia` → subtítulo · `estado` → etiqueta superior · `tags` → metadatos de portada. La fecha de generación se añade automáticamente.

## Personalizar la marca

Todo el estilo se controla sin tocar código:

- **`brand.json`** — colores, fuentes, texto del pie, logo.
- **logo** — opcional: pon un fichero (PNG/SVG/WebP) en `assets/` y apunta a él con `logo` en `brand.json`. Si `logo` está vacío, no se muestra ninguno.
- **`theme.css`** — tipografías, tablas, callouts, portada.

## Notas

- Los avisos de Obsidian (`> [!NOTE]`, `> [!WARNING]`, `> [!IMPORTANT]`, …) se renderizan como cajas de color.
- La portada no lleva cabecera/pie y no se numera; la numeración empieza en la primera página de contenido.
- Requiere Node 18+ y conexión a internet la primera vez (Chromium de Puppeteer).
