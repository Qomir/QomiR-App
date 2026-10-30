const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [,, url, outDir, mode, ...rest] = process.argv;
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: +(process.env.VW || 1080), height: +(process.env.VH || 1920) } });
  page.on('console', m => console.log('console:', m.text()));
  page.on('pageerror', e => console.log('pageerror:', e.message));
  await page.goto(url);
  await page.waitForFunction('window.ready === true', null, { timeout: 60000 });
  const stage = await page.$('#stage');
  const times = mode === 'stills' ? rest.map(Number) : null;
  const fps = 30;
  const n = times ? times.length : Math.round(await page.evaluate('window.TOTAL') * fps);
  const t0 = Date.now();
  for (let i = 0; i < n; i++) {
    const t = times ? times[i] : i / fps;
    await page.evaluate(t => window.setTime(t), t);
    const name = times ? `still_${t.toFixed(2)}.jpg` : `f${String(i).padStart(4, '0')}.png`;
    await stage.screenshot({ path: path.join(outDir, name), ...(times ? { type: 'jpeg', quality: 85 } : {}) });
    if (i % 30 === 0) console.log(`frame ${i}/${n} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  await browser.close();
})();
