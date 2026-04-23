#!/usr/bin/env node
/**
 * Usage: node scripts/screenshot.cjs <url> <out.png> [--user=<json>] [--width=1440] [--height=900]
 *
 * Captures a full-page PNG of a seerai page. Optional --user injects the
 * localStorage seerai_user record so the page loads past the switcher modal.
 * Example:
 *   node scripts/screenshot.cjs http://localhost:5174/exec /tmp/exec.png \
 *     --user='{"user_id":"marta.rossi","role":"exec","org_id":"initech","company":"initech"}'
 */
const { chromium } = require('playwright');

function arg(flag, def) {
  const m = process.argv.find(a => a.startsWith(flag + '='));
  return m ? m.slice(flag.length + 1) : def;
}

(async () => {
  const url = process.argv[2];
  const out = process.argv[3];
  if (!url || !out) {
    console.error('usage: screenshot.cjs <url> <out.png> [--user=json] [--tour=json] [--width=1440] [--height=900]');
    process.exit(2);
  }
  const user = arg('--user', null);
  const tour = arg('--tour', null);
  const clearTour = process.argv.includes('--clear-tour');
  const width = parseInt(arg('--width', '1440'), 10);
  const height = parseInt(arg('--height', '900'), 10);

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width, height } });
  const page = await ctx.newPage();

  // Seed localStorage before any app script runs.
  const origin = new URL(url).origin;
  await page.goto(origin + '/static/i18n.js').catch(() => {});  // navigate to a cheap origin asset
  await page.evaluate(({ user, tour, clearTour }) => {
    if (user) localStorage.setItem('seerai_user', user);
    if (clearTour) localStorage.removeItem('seerai_tour');
    if (tour) localStorage.setItem('seerai_tour', tour);
  }, { user, tour, clearTour });

  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const fullPage = !process.argv.includes('--viewport');
  await page.screenshot({ path: out, fullPage });
  await browser.close();
  console.error('wrote ' + out);
})();
