import { test, expect } from '@playwright/test';
import { installDoubles, expectResourcesReleased } from './browser-fixtures.js';

test.beforeEach(async ({ page }) => {
  await installDoubles(page);
  await page.goto('/');
});

async function load(page) {
  await page.getByRole('button', { name: 'Load speech test' }).click();
  await expect(page.getByRole('button', { name: 'Start reciting' })).toBeVisible();
}
async function record(page) {
  await load(page);
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
}
async function transcribe(page) {
  await record(page);
  await page.evaluate(() => window.testDevices.pushSamples(48_000));
  await page.getByRole('button', { name: 'Stop & transcribe' }).click();
  await expect(page.locator('#state-badge')).toHaveText('Working');
}

test('does not request microphone until deliberate Start; controls fit and are named', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Try Al-Ikhlas.' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('microphone stays off');
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Load speech test' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Start reciting' })).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const button = await page.getByRole('button', { name: 'Start reciting' }).boundingBox();
  expect(button.height).toBeGreaterThanOrEqual(44);
  expect(button.width).toBeGreaterThanOrEqual(44);
});

test('cancel while permission is pending stops a late stream and permits a fresh try', async ({ page }) => {
  await load(page);
  await page.evaluate(() => { window.testDevices.permission = 'pending'; });
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect.poll(() => page.evaluate(() => !!window.testDevices.resolvePermission)).toBe(true);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.evaluate(() => window.testDevices.resolvePermission());
  await expectResourcesReleased(page, expect);
  await expect(page.locator('#mic-label')).toHaveText('Microphone off');
  await expect(page.locator('#result-panel')).toBeHidden();
  await page.evaluate(() => { window.testDevices.permission = 'allow'; });
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expectResourcesReleased(page, expect);
});

test('permission refusal is recoverable and never becomes a recitation result', async ({ page }) => {
  await load(page);
  await page.evaluate(() => { window.testDevices.permission = 'deny'; });
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect(page.getByRole('status')).toContainText('denied');
  await expectResourcesReleased(page, expect);
  await expect(page.locator('#result-panel')).toBeHidden();
  await page.evaluate(() => { window.testDevices.permission = 'allow'; });
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
});

test('a cancelled permission request resolving during a fresh capture cannot stop the new capture', async ({ page }) => {
  await load(page);
  await page.evaluate(() => { window.testDevices.permission = 'pending'; });
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect.poll(() => page.evaluate(() => !!window.testDevices.resolvePermission)).toBe(true);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.evaluate(() => { window.testDevices.permission = 'allow'; });
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
  await page.evaluate(() => window.testDevices.resolvePermission());
  await expect.poll(() => page.evaluate(() => window.testDevices.streams.map(
    (stream) => stream.getTracks()[0].stopped,
  ))).toEqual([false, true]);
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expectResourcesReleased(page, expect);
});

for (const reason of ['interrupted', 'suspended']) {
  test(`audio context ${reason} releases capture and permits a new recording`, async ({ page }) => {
    await record(page);
    await page.evaluate((state) => window.testDevices.interruptContext(state), reason);
    await expect(page.getByRole('status')).toContainText('microphone was interrupted');
    await expectResourcesReleased(page, expect);
    expect(await page.evaluate(() => window.testDevices.workers[0].messages.some(
      (message) => message.type === 'transcribe',
    ))).toBe(false);
    await expect(page.locator('#result-panel')).toBeHidden();
    await page.getByRole('button', { name: 'Start reciting' }).click();
    await expect(page.locator('#mic-label')).toHaveText('Microphone on');
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expectResourcesReleased(page, expect);
  });
}

test('device loss releases capture and provides a retry without grading', async ({ page }) => {
  await record(page);
  await page.evaluate(() => window.testDevices.loseDevice());
  await expect(page.getByRole('status')).toContainText('disconnected');
  await expectResourcesReleased(page, expect);
  await expect(page.getByRole('button', { name: 'Start reciting' })).toBeVisible();
  await expect(page.locator('#result-panel')).toBeHidden();
});

test('cancelling model download rejects a late ready response', async ({ page }) => {
  await page.evaluate(() => { window.testDevices.autoReady = false; });
  await page.getByRole('button', { name: 'Load speech test' }).click();
  await page.getByRole('button', { name: 'Cancel' }).click();
  expect(await page.evaluate(() => window.testDevices.workers[0].terminated)).toBe(true);
  await page.evaluate(() => window.testDevices.workers[0].emit({ type: 'ready' }));
  await expect(page.getByRole('button', { name: 'Load speech test' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start reciting' })).toBeHidden();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
});

test('stops capture before inference; cancelled inference cannot restore old text', async ({ page }) => {
  await transcribe(page);
  await expectResourcesReleased(page, expect);
  expect(await page.evaluate(() => window.testDevices.workers[0].messages.at(-1).audio.length)).toBe(16_000);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.evaluate(() => window.testDevices.workers[0].emit({ type: 'result', text: 'STALE', elapsedMs: 10 }));
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.locator('#result-panel')).toBeHidden();
  expect(await page.evaluate(() => window.testDevices.workers[0].terminated)).toBe(true);
});

test('displays uncertain output as text, then clears it without persistent storage', async ({ page }) => {
  const writes = [];
  page.on('request', (request) => { if (request.method() !== 'GET') writes.push(request.url()); });
  await transcribe(page);
  const output = '<img src=x onerror="window.injected=true"> untrusted guess';
  await page.evaluate((text) => window.testDevices.workers[0].emit({ type: 'result', text, elapsedMs: 100 }), output);
  await expect(page.locator('#transcript')).toHaveText(output);
  await expect(page.locator('#transcript')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('#transcript')).toHaveAttribute('lang', 'ar');
  await expect(page.locator('#transcript img')).toHaveCount(0);
  await expect(page.getByText('May be wrong. Not verified Qur’an text.')).toBeVisible();
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))
  ).toEqual({ local: 0, session: 0 });
  expect(writes).toEqual([]);
  await page.getByRole('button', { name: 'Clear result' }).click();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.locator('#result-panel')).toBeHidden();
});

test('capture is capped at thirty seconds and the microphone closes at the deadline', async ({ page }) => {
  await page.clock.install();
  await record(page);
  await page.evaluate(() => window.testDevices.pushSamples(48_000 * 31));
  await page.clock.fastForward(30_000);
  await expect(page.locator('#state-badge')).toHaveText('Working');
  await expectResourcesReleased(page, expect);
  expect(await page.evaluate(() => window.testDevices.workers[0].messages.at(-1).audio.length)).toBe(480_000);
});

test('leaving the page clears capture and worker; stale output is ignored', async ({ page }) => {
  await record(page);
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  await expectResourcesReleased(page, expect);
  expect(await page.evaluate(() => window.testDevices.workers[0].terminated)).toBe(true);
  await page.evaluate(() => window.testDevices.workers[0].emit({ type: 'result', text: 'STALE', elapsedMs: 10 }));
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.locator('#mic-label')).toHaveText('Microphone off');
});

test('model failure and timeout offer retry, never a score', async ({ page }) => {
  await page.clock.install();
  await transcribe(page);
  await page.clock.fastForward(180_000);
  await expect(page.getByRole('status')).toContainText('too long');
  await expect(page.getByRole('button', { name: 'Load speech test' })).toBeVisible();
  await expect(page.locator('#result-panel')).toBeHidden();
  await load(page);
  await page.evaluate(() => window.testDevices.workers.at(-1).emit({ type: 'error' }));
  await expect(page.getByRole('status')).toContainText('could not finish');
  await expectResourcesReleased(page, expect);
});
