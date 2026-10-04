import { chromium, expect } from '@playwright/test';

// Real microphone APIs + real local model, but synthetic browser microphone.
// This checks integration and network routing, not recitation accuracy.
const browser = await chromium.launch({
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
});
try {
  const page = await browser.newPage();
  const failures = [];
  const writes = [];
  page.on('requestfailed', request => failures.push(request.url().split('?')[0]));
  page.on('request', request => {
    if (!['GET', 'HEAD'].includes(request.method())) writes.push(request.method());
  });
  await page.goto('http://127.0.0.1:4174');
  await page.locator('#load').click();
  await expect(page.locator('#start')).toBeVisible({ timeout: 180000 });
  await page.locator('#start').click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
  await expect(page.locator('#timer')).toHaveText('0:02 / 0:30', { timeout: 10000 });
  await page.locator('#stop').click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone off');
  await expect(page.locator('#status')).toContainText(/Done\.|No words were recognized/, { timeout: 180000 });
  await page.screenshot({ path: '/workspace/scratch/ikhlas-test.png', fullPage: true });
  console.log(JSON.stringify({ integration: 'pass', requestFailures: failures, nonReadRequests: writes }));
  if (failures.length || writes.length) process.exitCode = 1;
} finally { await browser.close(); }
