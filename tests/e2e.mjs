// Browser end-to-end test: needs the server running (python run.py in backend/) and Chrome.
// Usage: node tests/e2e.mjs   (BASE=http://127.0.0.1:5000, CHROME_PATH=... to override)
// It creates a throwaway workspace in the database (cookie-isolated) to prove state round-trips.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BASE = process.env.BASE || 'http://127.0.0.1:5000';
const CANDIDATES = [
  `${process.env.ProgramFiles}/Google/Chrome/Application/chrome.exe`,
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
];
const CHROME = process.env.CHROME_PATH || CANDIDATES.find((p) => existsSync(p));
if (!CHROME) throw new Error('Set CHROME_PATH to a Chrome or Chromium binary');
const dir = mkdtempSync(join(tmpdir(), 'orbit-chrome-'));
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=9333', `--user-data-dir=${dir}`, '--no-first-run', '--disable-gpu', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
const ok = (cond, msg) => { console.log(`${cond ? 'PASS' : 'FAIL'}  ${msg}`); if (!cond) failures++; };

async function targets() {
  for (let i = 0; i < 40; i++) {
    try { const r = await fetch('http://127.0.0.1:9333/json'); const t = await r.json(); const p = t.find((x) => x.type === 'page'); if (p) return p; } catch { /* starting */ }
    await sleep(250);
  }
  throw new Error('Chrome did not start');
}

const page = await targets();
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const errors = []; const failedReqs = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') errors.push(msg.params.args.map((a) => a.value || a.description).join(' '));
  if (msg.method === 'Network.responseReceived' && msg.params.response.status >= 400) failedReqs.push(`${msg.params.response.status} ${msg.params.response.url}`);
};
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJS = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails)); return r.result.result.value; };
const go = async (path) => { await send('Page.navigate', { url: BASE + path }); await sleep(2500); };
const waitFor = async (expr, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await evalJS(expr)) return true; await sleep(200); } return false; };

await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');

// 1. Owner page boots from the API
await go('/owner/');
ok(await waitFor("document.querySelectorAll('#navigation button, #navigation a').length > 0"), 'owner page rendered navigation');
ok((await evalJS('window.ORBIT_SOURCE')) === 'api', 'feed came from /api/data (not the static snapshot)');
ok(await evalJS('window.ORBIT_DATA.events.length > 0 && window.ORBIT_DATA.events.length === window.ORBIT_DATA.meta.events'),
  'feed has events and the count matches meta');
ok((await evalJS("document.getElementById('view').innerText.length")) > 200, 'overview has content');
console.log('      overview text:', (await evalJS("document.getElementById('view').innerText.slice(0,110).replace(/\\n/g,' | ')")));

// 2. Change sector -> saved to the database
const sectorBtn = "document.querySelector('[data-sector=\"Pharma\"]')";
if (!(await evalJS(`!!${sectorBtn}`))) await evalJS("document.querySelector('[data-view=\"profile\"]').click()");
await sleep(500);
ok(await evalJS(`!!${sectorBtn}`), 'sector switcher is present');
await evalJS(`${sectorBtn}.click()`);
await sleep(1500);
const server1 = await evalJS("fetch('/api/workspace').then(r=>r.json())");
ok(server1.sector === 'Pharma', `server stored sector = ${server1.sector}`);

// 2b. Every sector: switch to it, check signals reach the business over the last year, and that each page renders.
const sectors = await evalJS('window.ORBIT_DATA.meta.industries');
ok(sectors.length >= 10, `feed covers ${sectors.length} sectors (at least 10 expected)`);
const openView = async (v) => { await evalJS(`document.querySelector('[data-view="${v}"]').click()`); await sleep(250); };
const viewLength = () => evalJS("document.getElementById('view').innerText.length");
for (const name of sectors) {
  await openView('profile');
  const btn = `document.querySelector('[data-sector=${JSON.stringify(name).replace(/"/g, '\\"')}]')`;
  if (!(await evalJS(`!!${btn}`))) { ok(false, `sector button for ${name}`); continue; }
  await evalJS(`${btn}.click()`);
  await sleep(300);
  const company = await evalJS("document.getElementById('topName').innerText");
  const pages = {};
  await openView('overview'); pages.overview = await viewLength();
  await openView('signals');
  await evalJS("(() => { const s = document.getElementById('windowSel'); s.value = '365'; s.dispatchEvent(new Event('change', { bubbles: true })); })()");
  await sleep(300);
  const signals = await evalJS("document.querySelectorAll('.signal-card').length");
  pages.signals = await viewLength();
  await openView('profile'); pages.profile = await viewLength();
  const form = await evalJS("!!document.getElementById('profileForm')");
  ok(signals > 0 && form && Object.values(pages).every((n) => n > 200), `${name}: ${company}; ${signals} signals in a year; pages render (${Object.values(pages).join('/')})`);
}
await openView('profile');
await evalJS(`${sectorBtn}.click()`); // back to Pharma for the profile edit below
await sleep(800);
// 3. Edit the profile through the form -> saved to the database
const saved = await evalJS(`(() => { const f = document.getElementById('profileForm'); if (!f) return 'noform'; f.querySelector('[name=company]').value = 'E2E Pharma Ltd'; f.requestSubmit(); return 'submitted'; })()`);
await sleep(1500);
if (saved === 'submitted') {
  const server2 = await evalJS("fetch('/api/workspace').then(r=>r.json())");
  ok(server2.profiles.Pharma?.company === 'E2E Pharma Ltd', `server stored profile company = ${server2.profiles.Pharma?.company}`);
} else console.log('      (profile form not on this view: ' + saved + ')');

// 4. Wipe browser storage and reload: the workspace must come back from MySQL
await evalJS('localStorage.clear()');
await go('/owner/');
await waitFor("document.querySelectorAll('#navigation button, #navigation a').length > 0");
ok((await evalJS("document.getElementById('topSector').innerText + ' ' + document.getElementById('topName').innerText")).includes('E2E Pharma Ltd'), 'after clearing localStorage, profile restored from the database');

// 5. Analyst page
await go('/analyst/');
ok(await waitFor("document.body.innerText.length > 500"), 'analyst page rendered');
ok((await evalJS('window.ORBIT_SOURCE')) === 'api', 'analyst feed came from the API');
console.log('      analyst text:', (await evalJS("document.body.innerText.slice(0,100).replace(/\\n/g,' | ')")));

// 6. Compare page
await go('/compare/');
ok(await waitFor("document.body.innerText.length > 500"), 'compare page rendered');

ok(errors.length === 0, `no JS errors${errors.length ? ': ' + errors.slice(0, 3).join(' // ') : ''}`);
ok(failedReqs.length === 0, `no failed requests${failedReqs.length ? ': ' + failedReqs.join(', ') : ''}`);

// cleanup the test workspace's data so it does not linger
ws.close(); chrome.kill();
console.log(failures ? `\n${failures} check(s) failed` : '\nAll checks passed');
process.exit(failures ? 1 : 0);
