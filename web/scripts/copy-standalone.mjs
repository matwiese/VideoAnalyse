// Kopiert die Einzeldatei-App nach api/static/index.html (Vollversion: python -m api).
import { copyFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const src = fileURLToPath(new URL('../dist-standalone/index.html', import.meta.url));
const dir = fileURLToPath(new URL('../../api/static/', import.meta.url));
mkdirSync(dir, { recursive: true });
copyFileSync(src, dir + 'index.html');
console.log('kopiert nach api/static/index.html');
