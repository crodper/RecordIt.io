import fs from 'node:fs';
import { PDFDocument, PDFName, PDFArray, PDFDict, PDFString, PDFHexString, PDFRef } from 'pdf-lib';

const doc = await PDFDocument.load(fs.readFileSync(process.argv[2]));
const pages = doc.getPages();
const refIndex = new Map();
pages.forEach((p, i) => refIndex.set(p.ref.toString(), i));

const norm = (o) => {
  if (o instanceof PDFName) return o.asString().replace(/^\//, '');
  if (o instanceof PDFString || o instanceof PDFHexString) return o.asString ? o.asString() : o.decodeText();
  return String(o);
};

// mapa de destinos nombrados -> índice de página
const cat = doc.catalog;
const dests = cat.lookupMaybe(PDFName.of('Dests'), PDFDict);
const destMap = new Map();
if (dests) {
  for (const [key, val] of dests.entries()) {
    let v = val instanceof PDFRef ? doc.context.lookup(val) : val;
    let arr = v instanceof PDFArray ? v : (v instanceof PDFDict ? v.lookup(PDFName.of('D'), PDFArray) : null);
    if (!arr) continue;
    let pageRef = arr.get(0);
    const idx = refIndex.get(pageRef.toString());
    destMap.set(norm(key), idx);
  }
}

let total = 0, resolved = 0;
const rows = [];
pages.forEach((page, fromIdx) => {
  const an = page.node.Annots();
  if (!an) return;
  for (let i = 0; i < an.size(); i++) {
    let a; try { a = an.lookup(i, PDFDict); } catch { continue; }
    if (!a) continue;
    const st = a.lookup(PDFName.of('Subtype'));
    if (!st || st.toString() !== '/Link') continue;
    let d = a.lookup(PDFName.of('Dest'));
    if (!d) { const act = a.lookup(PDFName.of('A'), PDFDict); if (act) d = act.lookup(PDFName.of('D')); }
    if (!d) continue;
    total++;
    let toIdx;
    if (d instanceof PDFArray) { toIdx = refIndex.get(d.get(0).toString()); }
    else { toIdx = destMap.get(norm(d)); }
    if (toIdx !== undefined) resolved++;
    rows.push(`  pág ${fromIdx + 1} → destino "${norm(d)}" → ${toIdx !== undefined ? 'pág ' + (toIdx + 1) : '❌ NO RESUELVE'}`);
  }
});

console.log(`Destinos nombrados en el doc: ${destMap.size}`);
console.log(`Enlaces con destino: ${total} | resuelven a una página: ${resolved}`);
console.log(rows.join('\n'));
console.log(resolved === total && total > 0 ? '\n✅ TODOS los enlaces resuelven a una página real' : '\n❌ Hay enlaces que no resuelven');
