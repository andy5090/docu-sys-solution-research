import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// Original vector geometry; no font files or remote assets are required by logos.
const root = path.dirname(fileURLToPath(import.meta.url));
const ink = '#4747B3';
const accent = '#6262C4';
const tint = '#C9C9FF';
const concepts = [
  { id: '01-g-link', name: 'G Link', note: 'A distinctive G. A connected point.',
    icon: (a, b) => `<path d="M82 26H57C37 26 24 40 24 61V73C24 94 37 105 58 105H77C97 105 106 94 106 75V65H68" fill="none" stroke="${a}" stroke-width="16" stroke-linecap="square" stroke-linejoin="round"/><rect x="97" y="17" width="18" height="18" rx="5" fill="${b}"/>` },
  { id: '02-doc-dialogue', name: 'Doc Dialogue', note: 'From source documents to conversation.',
    icon: (a, b) => `<path d="M35 17H84L105 38V82C105 94 98 101 86 101H58L35 116V101H30C19 101 14 94 14 83V37C14 24 22 17 35 17Z" fill="none" stroke="${a}" stroke-width="10" stroke-linejoin="round"/><path d="M82 19V40H103M36 60H81M36 78H64" fill="none" stroke="${a}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/><circle cx="105" cy="98" r="13" fill="${b}"/>` },
  { id: '03-knowledge-grid', name: 'Knowledge Grid', note: 'Separate sources. One coherent answer.',
    icon: (a, b) => `<path d="M40 28H81Q100 28 100 47V82Q100 101 81 101H46Q27 101 27 82V53" fill="none" stroke="${a}" stroke-width="11" stroke-linecap="round"/><path d="M28 28L64 65H98M64 65V99" fill="none" stroke="${a}" stroke-width="10" stroke-linejoin="round"/><rect x="13" y="13" width="30" height="30" rx="9" fill="${b}"/><circle cx="99" cy="28" r="11" fill="${a}"/><circle cx="28" cy="100" r="11" fill="${a}"/>` }
];

const letters = [
  ['M55 14C45 1 23 0 12 14C1 27 1 48 12 61C23 75 47 75 59 60V39H36', 79],
  ['M0 39H21', 40],
  ['M0 5V69M49 5V69M0 37H49', 69],
  ['M0 44H44C44 16 0 16 0 44C0 68 23 78 43 63', 63],
  ['M46 12C35 0 5 0 5 20C5 42 48 30 48 52C48 75 17 79 0 63', 66],
  ['M46 12C35 0 5 0 5 20C5 42 48 30 48 52C48 75 17 79 0 63', 58]
];
const subletters = [
  ['M0 24L9 0L18 24M4 15H14', 25], ['M0 0V24', 16],
  ['', 10], ['M0 24L9 0L18 24M4 15H14', 25],
  ['M15 8V26C15 35 4 35 1 31M15 11C10 5 0 7 0 16C0 25 10 28 15 21', 23],
  ['M0 16H15C15 4 0 4 0 16C0 25 10 28 15 22', 23],
  ['M0 24V8M0 13C4 5 15 5 15 15V24', 23],
  ['M5 1V19C5 24 9 25 13 23M0 8H13', 16]
];
function glyphs(data, color, width) {
  let x = 0;
  return `<g fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round">${data.map(([d, advance]) => { const s = d ? `<path transform="translate(${x} 0)" d="${d}"/>` : ''; x += advance; return s; }).join('')}</g>`;
}
function wordmark(color = ink, detail = accent) {
  return `<g transform="translate(10 9)">${glyphs(letters, color, 9.5)}<g transform="translate(2 98) scale(.72)">${glyphs(subletters, detail, 2.7)}</g></g>`;
}
function svg(w, h, title, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="title"><title id="title">${title}</title>${body}</svg>\n`;
}
function lockup(c, color = ink, detail = accent) {
  return `<g transform="translate(8 12)">${c.icon(color, detail)}</g><g transform="translate(171 8)">${wordmark(color, detail)}</g>`;
}
for (const c of concepts) {
  const dir = path.join(root, c.id);
  await mkdir(dir, { recursive: true });
  for (const [suffix, a, b] of [['', ink, accent], ['-white', '#FFFFFF', tint], ['-mono', ink, ink]]) {
    await writeFile(path.join(dir, `icon${suffix}.svg`), svg(128, 128, `G-HeSS AI Agent — ${c.name} icon`, c.icon(a, b)));
    await writeFile(path.join(dir, `wordmark${suffix}.svg`), svg(396, 142, 'G-HeSS AI Agent', wordmark(a, b)));
    await writeFile(path.join(dir, `logo-horizontal${suffix}.svg`), svg(584, 160, `G-HeSS AI Agent — ${c.name}`, lockup(c, a, b)));
  }
  await writeFile(path.join(dir, 'app-icon.svg'), svg(192, 192, `G-HeSS AI Agent — ${c.name} app icon`, `<rect width="192" height="192" rx="44" fill="${ink}"/><g transform="translate(32 32)">${c.icon('#FFFFFF', tint)}</g>`));
}

const cards = concepts.map((c, i) => {
  const x = 60 + i * 450;
  return `<g transform="translate(${x} 244)">
    <rect width="420" height="606" rx="22" fill="#FFFFFF" stroke="#DCE3E4"/>
    <text x="28" y="43" font-size="12" letter-spacing="2" fill="#687C86">0${i + 1} / ${i === 0 ? 'PRIMARY PROPOSAL' : 'ALTERNATIVE'}</text>
    <g transform="translate(133 89) scale(1.2)">${c.icon(ink, accent)}</g>
    <g transform="translate(51 277) scale(.81)">${wordmark()}</g>
    <path d="M28 425H392" stroke="#E4EBED"/>
    <text x="28" y="464" font-size="25" font-weight="600" fill="${ink}">${c.name}</text>
    <text x="28" y="494" font-size="14" fill="#627782">${c.note}</text>
    <rect x="28" y="526" width="56" height="56" rx="14" fill="${ink}"/>
    <g transform="translate(34 532) scale(.34375)">${c.icon('#FFFFFF', tint)}</g>
    <g transform="translate(115 538) scale(.25)">${c.icon(ink, ink)}</g>
    <g transform="translate(174 542) scale(.1875)">${c.icon(ink, ink)}</g>
    <g transform="translate(225 546) scale(.125)">${c.icon(ink, ink)}</g>
    <text x="280" y="559" font-size="11" letter-spacing="1" fill="#627782">48 / 32 / 24 / 16</text>
  </g>`;
}).join('');
const board = svg(1440, 1080, 'G-HeSS AI Agent logo concepts', `
  <rect width="1440" height="1080" fill="#F5F5FA"/>
  <g font-family="DejaVu Sans, sans-serif">
    <text x="60" y="65" fill="${ink}" font-size="13" letter-spacing="3">G-HeSS AI Agent / VISUAL IDENTITY</text>
    <text x="57" y="145" fill="${ink}" font-size="57" font-weight="600">Logo explorations.</text>
    <text x="60" y="190" fill="#627782" font-size="18">Document intelligence. Clear answers. Connected knowledge.</text>
    ${cards}
    <rect x="60" y="886" width="1320" height="128" rx="20" fill="${ink}"/>
    <g transform="translate(90 899) scale(.63)">${lockup(concepts[0], '#FFFFFF', tint)}</g>
    <circle cx="1030" cy="950" r="17" fill="${accent}"/><circle cx="1080" cy="950" r="17" fill="${tint}"/><circle cx="1130" cy="950" r="17" fill="#FFFFFF"/>
    <text x="1181" y="955" fill="#E8E8FF" font-size="12" letter-spacing="1">#4747B3</text>
    <text x="60" y="1052" fill="#627782" font-size="11" letter-spacing="1">CUSTOM VECTOR LETTERING / TRANSPARENT SVG / LIGHT + DARK + MONO</text>
  </g>`);
await writeFile(path.join(root, 'preview.svg'), board);
console.log(`Generated ${concepts.length} logo families and preview.svg in ${root}`);
