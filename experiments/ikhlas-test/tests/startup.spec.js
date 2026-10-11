import { test, expect } from '@playwright/test';
import { installDoubles } from './browser-fixtures.js';

// Only microphone/model inference are doubled. The actual Rust WASM initializes.
test.beforeEach(async ({ page }) => {
  await installDoubles(page);
});

async function hold(page, pattern) {
  let release;
  let reached;
  let url;
  const gate = new Promise(resolve => { release = resolve; });
  const request = new Promise(resolve => { reached = resolve; });
  await page.route(pattern, async route => {
    url = route.request().url();
    reached();
    await gate;
    await route.continue().catch(() => {}); // A timeout may already abort this request.
  });
  return { request, release, url: () => url };
}

test('delayed Rust download leaves Load disabled until handlers and engine are ready', async ({ page }) => {
  const held = await hold(page, '**/hifz_core_bg.wasm');
  await page.goto('/');
  await held.request;
  await expect(page.locator('#status')).toContainText('Starting the app');
  await expect(page.locator('#load')).toBeDisabled();
  await expect(page.locator('#reload-app')).toBeHidden();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  expect(await page.evaluate(() => window.testDevices.workers.length)).toBe(0);
  held.release();
  await expect(page.locator('#load')).toBeEnabled();
  await page.locator('#load').click();
  await expect(page.locator('#start')).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
});

test('blocked app JavaScript explains the failure and reload recovers', async ({ page }) => {
  await page.route('**/app.js*', route => route.abort());
  await page.goto('/');
  await expect(page.locator('#status')).toContainText('app could not finish loading');
  await expect(page.locator('#load')).toBeDisabled();
  await expect(page.locator('#reload-app')).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  await page.unroute('**/app.js*');
  await page.locator('#reload-app').click();
  await expect(page.locator('#load')).toBeEnabled();
  await expect(page.locator('#reload-app')).toBeHidden();
  await page.locator('#load').click();
  await expect(page.locator('#start')).toBeVisible();
});

test('Rust download times out after fifteen seconds and offers reload without microphone access', async ({ page }) => {
  await page.clock.install();
  const held = await hold(page, '**/hifz_core_bg.wasm');
  await page.goto('/');
  await held.request;
  await page.clock.fastForward(15_001);
  await expect(page.locator('#status')).toContainText('practice engine could not load');
  await expect(page.locator('#load')).toBeDisabled();
  await expect(page.locator('#reload-app')).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  expect(await page.evaluate(() => window.testDevices.workers.length)).toBe(0);
  held.release();
  await page.unroute('**/hifz_core_bg.wasm');
  await page.locator('#reload-app').click();
  await expect(page.locator('#load')).toBeEnabled();
  await page.locator('#load').click();
  await expect(page.locator('#start')).toBeVisible();
});

test('a stalled app module reaches the independent startup deadline', async ({ page }) => {
  await page.clock.install();
  const held = await hold(page, '**/app.js*');
  await page.goto('/');
  await held.request;
  await expect(page.locator('#load')).toBeDisabled();
  await page.clock.fastForward(20_001);
  await expect(page.locator('#status')).toContainText('app could not finish loading');
  await expect(page.locator('#reload-app')).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  held.release();
  await page.evaluate(url => import(url), held.url());
  await expect(page.locator('#status')).toContainText('app could not finish loading');
  await expect(page.locator('#load')).toBeDisabled();
  await expect(page.locator('#reload-app')).toBeVisible();
});
