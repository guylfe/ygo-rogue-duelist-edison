const assert = require('node:assert/strict');
const { existsSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { chromium } = require('../tools/require-module.cjs').requireModule('playwright');

test('consolidated receipts use the acquired pack rarity in both reveal modes', async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage({ reducedMotion: 'reduce' });
    const web = path.join(__dirname, 'web');
    await page.route('https://edison.test/**', route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><body></body>' });
      if (!/^\/[a-z0-9-]+\.js$/.test(url.pathname)) return route.fulfill({ status: 404 });
      const file = path.join(web, url.pathname.slice(1));
      return existsSync(file) ? route.fulfill({ path: file, contentType: 'text/javascript' }) : route.fulfill({ status: 404 });
    });
    await page.goto('https://edison.test/');
    await page.evaluate(async () => {
      const { openPacks } = await import('/pack-opening.js');
      const id = 'DRAFT-JADEN-YUKI';
      const content = {
        packs: [{ id, name: 'Jaden Yuki', rare_display: [42] }],
        cards: [{ id: 42, name: 'Catalogue Rare' }, { id: 43, name: 'Receipt Rare' }],
      };
      window.present = () => openPacks({
        packs: [{ id, cards: [42, 43], rare_display: [43] }, { id, cards: [42] }],
        content, image: () => '', inspect() {},
      });
      window.present();
    });
    await page.locator('.pack-open').click();
    await page.locator('.pack-skip').click();
    assert.equal(await page.locator('.pack-pull.rare span').innerText(), 'Receipt Rare');
    assert.equal(await page.locator('.pack-pull.rare b').innerText(), 'RARE');
    await page.locator('.pack-close').click();

    await page.evaluate(() => window.present());
    await page.locator('.pack-open-all').click();
    const groups = page.locator('.pack-summary-group');
    assert.equal(await groups.nth(0).locator('.pack-summary-card.rare span').innerText(), 'Receipt Rare');
    assert.equal(await groups.nth(1).locator('.pack-summary-card.rare span').innerText(), 'Catalogue Rare');
  } finally {
    await browser.close();
  }
});
