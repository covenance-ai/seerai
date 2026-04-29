#!/usr/bin/env node
/**
 * Smoke-test the dashboard under a chosen seerai_lang locale.
 * Loads each page with a valid locale-native user (so cross-locale
 * identity issues don't mask page-level errors), captures pageerror /
 * console.error / 4xx-5xx HTTP responses, and reports them.
 *
 * Usage: node scripts/check_i18n.cjs [en|de|it|ru] [base-url]
 *
 * Note: assumes the local snapshots are loaded (DATA_SOURCE=local) — the
 * regression this guards against is per-locale data divergence.
 */
const { chromium } = require('playwright');

function pagesFor(user) {
  return [
    '/',
    '/exec',
    '/exec/costs',
    '/exec/insights',
    '/exec/analytics',
    '/exec/coach',
    '/exec/' + user.company,
    '/sessions/' + user.user_id,
    '/my/' + user.user_id,
    '/admin/privacy',
    '/faq',
  ];
}

// User per language. Local snapshot replaces the cast for non-en locales,
// so a US-name user_id won't exist in the ru snapshot and pages 404 on data.
// One representative exec per locale that exists in that locale's snapshot.
const USER_BY_LANG = {
  en: { user_id: 'alice.johnson', role: 'exec', org_id: 'acme-eng-backend', company: 'acme' },
  de: { user_id: 'oliver.braun', role: 'exec', org_id: 'kraftwerk-vertrieb', company: 'kraftwerk' },
  it: { user_id: 'giulia.rossi', role: 'exec', org_id: 'moda-design-prontomoda', company: 'moda' },
  ru: { user_id: 'alexander.egorov', role: 'exec', org_id: 'volga', company: 'volga' },
};

(async () => {
  const lang = process.argv[2] || 'ru';
  const base = process.argv[3] || 'http://localhost:8000';
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  // Seed localStorage with chosen language and a logged-in user.
  await page.goto(base + '/static/i18n.js').catch(() => {});
  const user = JSON.stringify(USER_BY_LANG[lang] || USER_BY_LANG.en);
  await page.evaluate(({ lang, user }) => {
    localStorage.setItem('seerai_lang', lang);
    localStorage.setItem('seerai_user', user);
  }, { lang, user });

  for (const path of pagesFor(USER_BY_LANG[lang] || USER_BY_LANG.en)) {
    const url = base + path;
    const issues = [];
    const onPageError = err => issues.push(['pageerror', String(err && err.stack || err)]);
    const onConsole = msg => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        issues.push([msg.type(), msg.text()]);
      }
    };
    const onResp = resp => {
      if (resp.status() >= 400) {
        issues.push(['http' + resp.status(), resp.url()]);
      }
    };
    page.on('pageerror', onPageError);
    page.on('console', onConsole);
    page.on('response', onResp);

    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(2500);
      // Trigger common interactions: click any tab/filter to surface
      // dynamically-rendered code paths that might break under i18n.
      try {
        await page.evaluate(() => {
          document.querySelectorAll('button[data-filter], .tab, .filter-btn').forEach((b, i) => {
            if (i < 3) try { b.click(); } catch (e) {}
          });
        });
        await page.waitForTimeout(500);
      } catch (e) {}
    } catch (e) {
      issues.push(['nav', String(e.message || e)]);
    }

    page.off('pageerror', onPageError);
    page.off('console', onConsole);
    page.off('response', onResp);

    console.log('\n=== ' + path + ' (' + lang + ') ===');
    if (!issues.length) {
      console.log('  ok');
    } else {
      for (const [t, m] of issues) console.log('  [' + t + '] ' + m.slice(0, 400));
    }
  }

  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
