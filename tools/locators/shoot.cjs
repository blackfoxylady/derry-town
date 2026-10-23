// Locators, step 2 of 3: render the frames listed by `manage.py render_locators export`.
//   node tools/locators/shoot.cjs build/locators [--only 12,town,mapcard-ru]
// Serves tools/locators/renderer, the export directory and atlas/static on a free local
// port, opens the reference renderer in headless Chromium (Playwright, a dev dependency)
// for every job and writes <export>/png/<name>.png plus png/views.json (the view actually
// used: the renderer page may shift a frame so the selected name fits). Step 3 (`render_locators pack`)
// turns them into WebP. Nothing here reaches the server or the Docker image.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };

function serve(exportDir) {
  const mounts = [['/static/atlas/', path.join(ROOT, 'atlas', 'static', 'atlas')],
    ['/data/', exportDir], ['/', path.join(__dirname, 'renderer')]];
  const server = http.createServer((req, res) => {
    let url;
    try { url = decodeURIComponent(new URL(req.url, 'http://x').pathname); } catch (e) { url = ''; }
    for (const [prefix, dir] of mounts) {
      if (!url.startsWith(prefix)) continue;
      const file = path.join(dir, url.slice(prefix.length) || 'index.html');
      const rel = path.relative(dir, file);
      if (!rel || rel.startsWith('..') || path.isAbsolute(rel) || !fs.existsSync(file) || !fs.statSync(file).isFile()) break;
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
      return;
    }
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

(async () => {
  const args = process.argv.slice(2);
  const exportDir = path.resolve(args[0] || path.join(ROOT, 'build', 'locators'));
  const onlyAt = args.indexOf('--only');
  const only = onlyAt > -1 ? args[onlyAt + 1].split(',') : null;
  const { jobs } = JSON.parse(fs.readFileSync(path.join(exportDir, 'jobs.json'), 'utf8'));
  const outDir = path.join(exportDir, 'png');
  fs.mkdirSync(outDir, { recursive: true });
  const viewsFile = path.join(outDir, 'views.json');
  const views = fs.existsSync(viewsFile) ? JSON.parse(fs.readFileSync(viewsFile, 'utf8')) : {};
  const server = await serve(exportDir);
  const base = `http://127.0.0.1:${server.address().port}/index.html?`;
  const browser = await chromium.launch();
  const contexts = new Map();   // one context per viewport size and density: pages are reused
  let done = 0;
  try {
    for (const job of jobs) {
      if (only && !only.some((o) => job.name === o || job.name.startsWith(o + '-'))) continue;
      const key = `${job.w}x${job.h}@${job.dpr}`;
      if (!contexts.has(key)) {
        const ctx = await browser.newContext({ viewport: { width: job.w, height: job.h }, deviceScaleFactor: job.dpr });
        contexts.set(key, await ctx.newPage());
      }
      const page = contexts.get(key);
      const qs = new URLSearchParams({ data: '/data/' + job.data, cx: job.cx, cy: job.cy, k: job.k, lang: job.lang });
      if (job.sel != null) qs.set('sel', job.sel);
      await page.goto(base + qs, { waitUntil: 'load' });
      await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
      await page.screenshot({ path: path.join(outDir, job.name + '.png'), animations: 'disabled' });
      views[job.name] = await page.evaluate(() => window.__view);
      if (++done % 50 === 0) console.log(done, 'frames');
    }
  } finally {
    fs.writeFileSync(viewsFile, JSON.stringify(views, null, 1));
    await browser.close();
    server.close();
  }
  console.log('done:', done, 'frames in', outDir);
})().catch((e) => { console.error(e); process.exit(1); });
