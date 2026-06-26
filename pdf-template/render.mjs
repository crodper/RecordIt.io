#!/usr/bin/env node
/* ============================================================
   Plantilla PDF — Markdown → PDF
   Uso:  node render.mjs <entrada.md> [salida.pdf]
   ============================================================ */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';
import MarkdownIt from 'markdown-it';
import anchor from 'markdown-it-anchor';
import puppeteer from 'puppeteer';
import { PDFDocument } from 'pdf-lib';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ---------- argumentos ----------
const input = process.argv[2];
if (!input) {
  console.error('Uso: node render.mjs <entrada.md> [salida.pdf]');
  process.exit(1);
}
const inputPath = path.resolve(input);
const output = process.argv[3]
  ? path.resolve(process.argv[3])
  : inputPath.replace(/\.md$/i, '') + '.pdf';

// ---------- recursos de marca ----------
const brand = JSON.parse(fs.readFileSync(path.join(__dirname, 'brand.json'), 'utf8'));
const css = fs.readFileSync(path.join(__dirname, 'theme.css'), 'utf8');
// El logo es opcional: si brand.logo está vacío o el fichero no existe, se omite.
let logoData = '';
if (brand.logo) {
  try {
    const logoPath = path.join(__dirname, brand.logo);
    const ext = path.extname(logoPath).slice(1).toLowerCase() || 'png';
    logoData = `data:image/${ext};base64,` + fs.readFileSync(logoPath).toString('base64');
  } catch { logoData = ''; }
}

// ---------- leer markdown + front-matter ----------
const raw = fs.readFileSync(inputPath, 'utf8');
let fm = {}, body = raw;
const fmMatch = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw);
if (fmMatch) {
  try { fm = yaml.load(fmMatch[1]) || {}; }
  catch (e) { console.warn('Aviso: front-matter no parseable:', e.message); }
  body = raw.slice(fmMatch[0].length);
}

// ---------- helpers ----------
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// slug estilo GitHub (para que la Tabla de contenidos del documento enlace bien)
const slugify = (s) => s.trim().toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s/g, '-');

// ---------- plugin: callouts de Obsidian ( > [!TIPO] Título ) ----------
const CALLOUT_ICON = { note:'ℹ', info:'ℹ', tip:'✦', important:'❗', warning:'⚠', caution:'⚠', danger:'⛔' };
const CALLOUT_LABEL = { note:'Nota', info:'Info', tip:'Consejo', important:'Importante', warning:'Aviso', caution:'Precaución', danger:'Peligro' };

function obsidianCallouts(md) {
  md.core.ruler.push('obsidian_callouts', (state) => {
    const tokens = state.tokens;
    for (let i = 0; i < tokens.length; i++) {
      if (tokens[i].type !== 'blockquote_open') continue;

      // primer token inline dentro de la cita
      let j = i + 1;
      while (j < tokens.length && tokens[j].type !== 'inline' && tokens[j].type !== 'blockquote_close') j++;
      if (j >= tokens.length || tokens[j].type !== 'inline') continue;
      const inline = tokens[j];

      const nl = inline.content.indexOf('\n');
      const firstLine = nl === -1 ? inline.content : inline.content.slice(0, nl);
      const m = /^\s*\[!(\w+)\]([-+])?\s*(.*)$/.exec(firstLine);
      if (!m) continue;

      const type = m[1].toLowerCase();
      const title = (m[3] || '').trim() || CALLOUT_LABEL[type] || type.toUpperCase();
      const icon = CALLOUT_ICON[type] || 'ℹ';

      // localizar blockquote_close emparejado
      let depth = 0, closeIdx = -1;
      for (let k = i; k < tokens.length; k++) {
        if (tokens[k].type === 'blockquote_open') depth++;
        else if (tokens[k].type === 'blockquote_close') { depth--; if (depth === 0) { closeIdx = k; break; } }
      }

      // convertir <blockquote> en <div class="callout callout-tipo">
      tokens[i].tag = 'div';
      tokens[i].attrSet('class', 'callout callout-' + type);
      tokens[i].markup = '';
      if (closeIdx >= 0) { tokens[closeIdx].tag = 'div'; tokens[closeIdx].markup = ''; }

      // quitar la línea del marcador del cuerpo y re-parsear
      inline.content = nl === -1 ? '' : inline.content.slice(nl + 1);
      state.md.inline.parse(inline.content, state.md, state.env, inline.children = []);

      // inyectar la cabecera del callout (icono + título)
      const titleTok = new state.Token('html_block', '', 0);
      titleTok.content =
        `<div class="callout-title"><span class="callout-icon">${icon}</span>` +
        `<span class="callout-label">${esc(title)}</span></div>\n`;
      tokens.splice(i + 1, 0, titleTok);
    }
  });
}

// ---------- markdown → html ----------
const md = new MarkdownIt({ html: true, linkify: true, typographer: false });
md.use(anchor, { slugify, tabIndex: false });
md.use(obsidianCallouts);

let bodyHtml = md.render(body);
// el título ya aparece en la portada → quitar el primer H1 del cuerpo
if (fm.title) bodyHtml = bodyHtml.replace(/<h1[^>]*>[\s\S]*?<\/h1>\s*/, '');

// ---------- variables de marca para el CSS ----------
const brandVars = ':root{' +
  Object.entries(brand.colors).map(([k, v]) => `--c-${k}:${v}`).join(';') +
  `;--font-body:${brand.fonts.body};--font-mono:${brand.fonts.mono};}`;

const head = `<meta charset="utf-8"><style>${brandVars}\n${css}</style>`;
const genDate = new Date().toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' });

// ---------- portada ----------
const metaRow = (k, v) => v ? `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>` : '';
const tagsRow = (Array.isArray(fm.tags) && fm.tags.length)
  ? `<tr><td>Etiquetas</td><td>${fm.tags.map(esc).join(' · ')}</td></tr>` : '';

const coverHtml = `<!doctype html><html lang="es"><head>${head}</head>
<body class="is-cover"><section class="cover">
  <div class="cover-top">${logoData ? `<img class="cover-logo" src="${logoData}" alt="">` : ''}</div>
  <div class="cover-main">
    ${fm.estado ? `<span class="cover-kicker">${esc(fm.estado)}</span>` : ''}
    <h1 class="cover-title">${esc(fm.title || path.basename(inputPath))}</h1>
    ${(fm.departamento || fm.audiencia) ? `<div class="cover-sub">${esc(fm.departamento || fm.audiencia)}</div>` : ''}
  </div>
  <div class="cover-meta">
    <div class="cover-band"></div>
    <table class="cover-meta-tbl"><tbody>
      ${metaRow('Dirigido a', fm.audiencia)}
      ${metaRow('Estado', fm.estado)}
      ${metaRow('Generado', genDate)}
      ${tagsRow}
    </tbody></table>
  </div>
</section></body></html>`;

// ---------- cuerpo ----------
const bodyDoc = `<!doctype html><html lang="es"><head>${head}</head>
<body><main class="content">${bodyHtml}</main></body></html>`;

// ---------- cabecera / pie (estilos en línea, requisito de Puppeteer) ----------
const hfBase = 'font-family:Lato,sans-serif;font-size:8px;color:#5b6b76;width:100%;padding:0 16mm;' +
  'display:flex;align-items:center;justify-content:space-between;';
const headerTemplate = `<div style="${hfBase}">
  ${logoData ? `<img src="${logoData}" style="height:40px;width:auto;">` : '<span></span>'}
  <span style="text-align:right;">${esc(brand.headerTitle || fm.title || '')}</span>
</div>`;
const footerTemplate = `<div style="${hfBase}">
  <span>${esc(brand.footerText || '')}</span>
  <span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span>
</div>`;

// ---------- render con Chromium ----------
const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--font-render-hinting=none'],
});

async function toPdf(html, opts) {
  const p = await browser.newPage();
  await p.setContent(html, { waitUntil: 'networkidle0' });
  const bytes = await p.pdf(opts);
  await p.close();
  return bytes;
}

const coverBytes = await toPdf(coverHtml, {
  format: 'A4', printBackground: true,
  margin: { top: '0', bottom: '0', left: '0', right: '0' },
});
const bodyBytes = await toPdf(bodyDoc, {
  format: 'A4', printBackground: true,
  displayHeaderFooter: true, headerTemplate, footerTemplate,
  margin: { top: '30mm', bottom: '18mm', left: '16mm', right: '16mm' },
});

await browser.close();

// ---------- unir: el CUERPO es el documento base (conserva su diccionario de
//            destinos nombrados /Dests → el índice queda clicable) y la PORTADA
//            se inserta como primera página, sin numerar.
//            (Crear un doc nuevo con copyPages perdía /Dests y rompía los enlaces.)
const finalDoc = await PDFDocument.load(bodyBytes);
const coverDoc = await PDFDocument.load(coverBytes);
const [coverPage] = await finalDoc.copyPages(coverDoc, [0]);
finalDoc.insertPage(0, coverPage);
fs.writeFileSync(output, await finalDoc.save());
console.log('✅ PDF generado:', output, `(${finalDoc.getPageCount()} páginas)`);
