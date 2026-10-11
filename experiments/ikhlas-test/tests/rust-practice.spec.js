import { test, expect } from '@playwright/test';
import { installDoubles, expectResourcesReleased } from './browser-fixtures.js';

// Recognition and capture are doubles; selection/comparison use the real Rust WASM.
test.beforeEach(async ({ page }) => {
  await installDoubles(page);
  await page.goto('/');
  await page.evaluate(() => {
    [30,52,52,44,28,28,20,56,40,31,50].forEach((count, index) => {
      for (let ayah = 1; ayah <= count; ayah++) {
        window.testDevices.records.push({ surah: 67 + index, ayah,
          text_uthmani: `${ayah === 1 ? 'alpha beta gamma omega ' : ''}item${index}a${ayah} tail${index}a${ayah}` });
      }
    });
  });
  await page.locator('#load').click();
  await expect(page.locator('#start')).toBeVisible();
});

async function options(page) {
  await page.locator('.practice-options summary').click();
}
async function recite(page, text) {
  await page.locator('#start').click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
  await page.evaluate(() => window.testDevices.pushSamples(48_000));
  await page.locator('#stop').click();
  await expect(page.locator('#state-badge')).toHaveText('Working');
  await page.evaluate(text => window.testDevices.workers.at(-1).emit({ type: 'result', text }), text);
}

test('a selected range uses only those verses and hides its cue on capture', async ({ page }) => {
  await options(page);
  await page.locator('#verse-first').fill('2');
  await page.locator('#verse-last').fill('2');
  await page.locator('#verse-last').press('Tab');
  await page.locator('#reveal').click();
  await expect(page.locator('#cue-text')).toHaveText('delta elm fern');
  await recite(page, 'delta elm fern');
  await expect(page.locator('#cue')).toBeHidden();
  await expect(page.locator('#cue-text')).toBeEmpty();
  await expect(page.locator('#reference-verses p')).toHaveCount(1);
  await expect(page.locator('#reference-verses p')).toHaveText('delta elm fern');
  await expect(page.locator('#word-findings')).toBeEmpty();
  await expect(page.locator('#word-summary')).toContainText('does not prove correct recitation');
  await expect(page.locator('#session-count')).toHaveText('1');
  await expectResourcesReleased(page, expect);
});

test('invalid range never requests microphone or produces feedback', async ({ page }) => {
  await options(page);
  await page.locator('#verse-first').fill('4');
  await page.locator('#verse-last').fill('2');
  await page.locator('#start').click();
  await expect(page.locator('#status')).toContainText('valid verse range');
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  await expect(page.locator('#result-panel')).toBeHidden();
  await expect(page.locator('#session-count')).toHaveText('0');
});

test('random Juz 29 practice stays in scope and respects verse-count boundaries', async ({ page }) => {
  await options(page);
  await page.locator('#scope').selectOption('juz29');
  await page.locator('#practice-length').selectOption('2');
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.locator('#random').click();
    const values = await page.evaluate(() => ['surah','verse-first','verse-last'].map(id => Number(document.getElementById(id).value)));
    const [surah, first, last] = values;
    expect(surah).toBeGreaterThanOrEqual(67);
    expect(surah).toBeLessThanOrEqual(77);
    expect(first).toBeGreaterThanOrEqual(1);
    expect(last).toBeGreaterThanOrEqual(first);
    expect(last - first).toBeLessThan(2);
    expect(last).toBeLessThanOrEqual([30,52,52,44,28,28,20,56,40,31,50][surah - 67]);
    await expect(page.locator('#basmala')).not.toBeChecked();
    await expect(page.locator('#result-panel')).toBeHidden();
  }
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
});

test('next passage clears feedback and cue, retains session count only until reload', async ({ page }) => {
  await options(page);
  await page.locator('#verse-first').fill('2');
  await page.locator('#verse-last').fill('2');
  await page.locator('#verse-last').press('Tab');
  await recite(page, 'delta elm fern');
  await page.locator('#reveal').click();
  await expect(page.locator('#cue')).toBeVisible();
  await page.locator('#next-practice').click();
  await expect(page.locator('#result-panel')).toBeHidden();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.locator('#word-findings')).toBeEmpty();
  await expect(page.locator('#cue')).toBeHidden();
  await expect(page.locator('#session-count')).toHaveText('1');
  await expect(page.locator('#surah')).toHaveValue('112');
  await page.reload();
  await expect(page.locator('#session-count')).toHaveText('0');
});

test('changing a verse range during capture releases microphone and rejects stale output', async ({ page }) => {
  await options(page);
  await page.locator('#start').click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
  await page.locator('#verse-last').fill('3');
  await page.locator('#verse-last').press('Tab');
  await expectResourcesReleased(page, expect);
  expect(await page.evaluate(() => window.testDevices.workers[0].terminated)).toBe(true);
  await page.evaluate(() => window.testDevices.workers[0].emit({ type: 'result', text: 'old output' }));
  await expect(page.locator('#result-panel')).toBeHidden();
  await expect(page.locator('#session-count')).toHaveText('0');
  await expect(page.locator('#load')).toBeVisible();
});

test('failed Rust engine load offers a working reload without microphone access', async ({ page }) => {
  await page.route('**/hifz_core_bg.wasm', route => route.abort());
  await page.reload();
  await expect(page.locator('#status')).toContainText('practice engine could not load');
  await expect(page.locator('#load')).toBeDisabled();
  await expect(page.locator('#reload-app')).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  expect(await page.evaluate(() => window.testDevices.workers.length)).toBe(0);
  await page.unroute('**/hifz_core_bg.wasm');
  await page.locator('#reload-app').click();
  await expect(page.locator('#load')).toBeEnabled();
  await expect(page.locator('#reload-app')).toBeHidden();
  await page.locator('#load').click();
  await expect(page.locator('#start')).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
});

for (const corruption of ['missing', 'malformed']) {
  test(`random scope rejects a ${corruption} source instead of silently choosing another surah`, async ({ page }) => {
    await page.evaluate(corruption => {
      const records = window.testDevices.records;
      const index = records.findIndex(r => r.surah === 67 && r.ayah === 1);
      if (corruption === 'missing') records.splice(index, 1);
      else records[index].text_uthmani = ' ';
    }, corruption);
    await options(page);
    await page.locator('#scope').selectOption('juz29');
    await page.locator('#random').click();
    await expect(page.locator('#status')).toContainText('could not be prepared');
    await expect(page.locator('#surah')).toHaveValue('112');
    await expect(page.locator('#verse-first')).toHaveValue('1');
    await expect(page.locator('#verse-last')).toHaveValue('4');
    await expect(page.locator('#result-panel')).toBeHidden();
    expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  });
}
