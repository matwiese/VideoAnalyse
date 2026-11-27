const { chromium } = require('playwright');
const fs = require('fs');
// End-to-End-Test Video-Tracker: node web/e2e/tracker.e2e.cjs <video.mp4>  (Vollversion muss auf :8000 laufen)
const VIDEO = process.argv[2] || 'sprung_zeitlupe.mp4';
const T = JSON.parse(fs.readFileSync(VIDEO + '.truth.json'));
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1700, height: 1100 } });
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto('http://127.0.0.1:8000/', { waitUntil: 'load' });
  await p.waitForTimeout(1500);
  await p.getByRole('button', { name: 'Video-Tracker' }).click();
  await p.locator('input[type=file][accept^="video"]').setInputFiles(VIDEO);
  await p.waitForSelector('text=1 · Bildrate', { timeout: 30000 });
  await p.waitForTimeout(2500);
  console.log('fps-Hinweis:', (await p.locator('.tracker-side .footnote').nth(2).innerText()).slice(0, 80));
  const fpsInputs = p.locator('.tracker-side details').nth(0).locator('input');
  console.log('Datei-fps', await fpsInputs.nth(0).inputValue());
  await fpsInputs.nth(1).fill('240');
  const cv = p.locator('.tracker-canvas canvas').first();
  const box = await cv.boundingBox();
  const sc = box.width / 1280;
  const clickPx = async (u, v) => { await cv.click({ position: { x: u * sc, y: v * sc }, force: true }); };
  // Kalibrierung
  await p.getByRole('button', { name: /Maßstab: 2 Punkte/ }).click();
  await clickPx(...T.scale[0]); await clickPx(...T.scale[1]);
  await p.locator('.tracker-side details').nth(2).locator('input[type=number]').fill('1');
  await p.getByLabel(/Strecke ist waagrecht/).check();
  await p.getByRole('button', { name: /Brettspitze in Ruhe klicken/ }).click();
  await clickPx(...T.origin);
  console.log('Kalibrierung:', await p.locator('.tracker-side details').nth(2).locator('.mono').innerText());
  // Punkte
  const labels = { board_tip: 'Brettspitze', toe: 'Zehenspitze', ball: 'Ballen', heel: 'Ferse', ankle: 'Sprunggelenk', knee: 'Knie', hip: 'Hüfte', shoulder: 'Schulter', vertex: 'Kopf', elbow: 'Ellbogen', wrist: 'Handgelenk' };
  const slider = p.locator('input[aria-label="Bild"]');
  let manual = 0;
  const t0 = Date.now();
  for (const [id, lab] of Object.entries(labels)) {
    await slider.fill('0'); await p.waitForTimeout(150);
    await p.locator('.point', { hasText: lab }).click();
    await clickPx(...T.gt_px[id][0]); manual++;
    for (let guard = 0; guard < 40; guard++) {
      await p.getByRole('button', { name: /Automatisch weiter/ }).click();
      await p.waitForSelector('.tracker-side button:has-text("Stopp")', { timeout: 5000 }).catch(() => {});
      await p.waitForSelector('.tracker-side button:has-text("Automatisch weiter")', { timeout: 600000 });
      const msg = await p.locator('.tracker-main .warning').innerText().catch(() => '');
      if (msg.includes('Bereichsende')) break;
      const m = msg.match(/Bild (\d+)/);
      if (!m) break;
      const f = Number(m[1]);
      const g = T.gt_px[id][f];
      if (g[0] < 3 || g[1] < 3 || g[0] > 1277 || g[1] > 717) break; // Punkt außerhalb des Bildes
      await clickPx(...g); manual++; // Korrektur wie ein Mensch
      if (f >= T.n - 1) break;
    }
    const cnt = await p.locator('.point', { hasText: lab }).locator('.cnt').innerText();
    console.log(id, cnt);
  }
  console.log('manuelle Klicks', manual, 'Zeit s', ((Date.now() - t0) / 1000).toFixed(0));
  // Genauigkeit gegen Wahrheit (Projekt aus localStorage)
  const proj = await p.evaluate(() => { const k = Object.keys(localStorage).find((x) => x.startsWith('tracker:v1:')); return JSON.parse(localStorage.getItem(k)); });
  for (const id of Object.keys(labels)) {
    const tr = proj.tracks[id] || {}; let s = 0, n = 0, mx = 0;
    for (const [f, uv] of Object.entries(tr)) { const g = T.gt_px[id][Number(f)]; const e = Math.hypot(uv[0] - g[0], uv[1] - g[1]); s += e * e; n++; mx = Math.max(mx, e); }
    console.log(`  ${id}: RMS ${(Math.sqrt(s / n)).toFixed(2)} px (${(Math.sqrt(s / n) * 4).toFixed(1)} mm), max ${mx.toFixed(1)} px, n=${n}`);
  }
  await p.screenshot({ path: VIDEO + '.tracker.png' });
  await p.getByRole('button', { name: 'An Analyse übergeben' }).click();
  await p.waitForTimeout(500);
  await p.getByRole('button', { name: /^Analysieren/ }).click();
  await p.waitForSelector('.cards4', { timeout: 60000 });
  const cards = await p.locator('.cards4 .card').allInnerTexts();
  console.log('Analyse:', cards.map((c) => c.replace(/\n/g, ' ')).join(' | '));
  const tm = T.truth_metrics;
  console.log('Wahrheit: Kontakt', tm.t_contact.toFixed(3), 'v_z,TO', tm.v_z_to.toFixed(2), 'v_x,TO', tm.v_x_to.toFixed(2), 'H_y', tm.H_y.toFixed(1), 'Hauptmax', tm.F_active_peak_bw.toFixed(2));
  await p.screenshot({ path: VIDEO + '.analyse.png' });
  console.log('ERRS', JSON.stringify(errs.slice(0, 5)));
  await b.close();
})();
