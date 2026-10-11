import { test, expect } from '@playwright/test';
import { installDoubles, expectResourcesReleased, syntheticRecords } from './browser-fixtures.js';

const ikhlas = syntheticRecords.filter(r => r.surah === 112).map(r => r.text_uthmani).join(' ');
const fatiha = syntheticRecords.filter(r => r.surah === 1).map(r => r.text_uthmani).join(' ');

test.beforeEach(async ({ page }) => {
  await installDoubles(page);
  await page.goto('/');
});

async function load(page) {
  await page.getByRole('button', { name: 'Load speech test' }).click();
  await expect(page.getByRole('button', { name: 'Start reciting' })).toBeVisible();
}

async function transcribe(page) {
  await page.getByRole('button', { name: /^(Start reciting|Try again)/ }).click();
  await expect(page.locator('#mic-label')).toHaveText('Microphone on');
  await page.evaluate(() => window.testDevices.pushSamples(48_000));
  await page.getByRole('button', { name: 'Stop & transcribe' }).click();
  await expect(page.locator('#state-badge')).toHaveText('Working');
}

async function emit(page, text) {
  await page.evaluate(text => window.testDevices.workers.at(-1).emit(
    { type: 'result', text, elapsedMs: 10 }), text);
}

test('final verse repeat is shown tentatively and pronunciation stays unsure', async ({ page }) => {
  await load(page);
  await transcribe(page);
  const hypothesis = ikhlas + ' jade kite larch moss';
  await emit(page, hypothesis);
  await expect(page.locator('#transcript')).toHaveText(hypothesis);
  await expect(page.locator('#word-findings')).toHaveText('Possible repeat: verse 4.');
  await expect(page.locator('#word-summary')).toContainText('Check these yourself');
  await expect(page.getByText('Pronunciation: unsure.', { exact: true })).toBeVisible();
  await expectResourcesReleased(page, expect);
});

test('interior skipped word uses its source position; a fresh unclear attempt clears findings', async ({ page }) => {
  await load(page);
  await transcribe(page);
  await emit(page, ikhlas.replace('birch ', ''));
  await expect(page.locator('#word-findings')).toHaveText('Possible skip: verse 1, source word 6.');
  await transcribe(page);
  await expect(page.locator('#word-findings')).toBeEmpty();
  await emit(page, ikhlas.replace('birch', 'unknown'));
  await expect(page.locator('#word-summary')).toContainText('Word check: unsure');
  await expect(page.locator('#word-findings')).toBeEmpty();
});

test('closing words are explicitly unassessed and Clear removes all feedback', async ({ page }) => {
  await load(page);
  await transcribe(page);
  await emit(page, ikhlas + ' extra closing');
  await expect(page.locator('#word-findings')).toHaveText('Closing words: unsure; not checked.');
  await expect(page.locator('#word-summary')).toContainText('does not prove correct recitation');
  await page.getByRole('button', { name: 'Clear result' }).click();
  for (const id of ['transcript', 'word-summary', 'word-findings', 'reference-verses']) {
    await expect(page.locator(`#${id}`)).toBeEmpty();
  }
  await expect(page.locator('#result-panel')).toBeHidden();
});

test('passage selection clears previous results and changes the comparison scope', async ({ page }) => {
  await load(page);
  await transcribe(page);
  await emit(page, ikhlas + ' jade kite larch moss');
  await page.getByRole('combobox', { name: 'Passage' }).selectOption('1');
  await expect(page.getByRole('checkbox')).toBeDisabled();
  await expect(page.locator('#result-panel')).toBeHidden();
  await expect(page.locator('#word-findings')).toBeEmpty();
  await transcribe(page);
  await emit(page, fatiha);
  await expect(page.locator('#word-summary')).toContainText('No clear whole-word skips');
  await expect(page.locator('#word-findings')).toBeEmpty();
  await expect(page.locator('#reference-verses p')).toHaveCount(7);
});

test('changing passage during inference terminates it and ignores late results', async ({ page }) => {
  await load(page);
  await transcribe(page);
  await page.getByRole('combobox', { name: 'Passage' }).selectOption('1');
  await expect(page.getByRole('button', { name: 'Load speech test' })).toBeVisible();
  expect(await page.evaluate(() => window.testDevices.workers[0].terminated)).toBe(true);
  await emit(page, ikhlas);
  await expect(page.locator('#result-panel')).toBeHidden();
  await expect(page.locator('#transcript')).toBeEmpty();
  await expect(page.locator('#word-summary')).toBeEmpty();
  await load(page);
  await transcribe(page);
  await page.evaluate(text => window.testDevices.workers[0].emit({ type: 'result', text }), ikhlas);
  await expect(page.locator('#state-badge')).toHaveText('Working');
  await emit(page, fatiha);
  await expect(page.locator('#transcript')).toHaveText(fatiha);
});

test('changing opening scope during permission request releases a late stream', async ({ page }) => {
  await load(page);
  await page.evaluate(() => { window.testDevices.permission = 'pending'; });
  await page.getByRole('button', { name: 'Start reciting' }).click();
  await expect.poll(() => page.evaluate(() => !!window.testDevices.resolvePermission)).toBe(true);
  await page.getByRole('checkbox').uncheck();
  await page.evaluate(() => window.testDevices.resolvePermission());
  await expectResourcesReleased(page, expect);
  await expect(page.getByRole('button', { name: 'Load speech test' })).toBeVisible();
  await expect(page.locator('#result-panel')).toBeHidden();
  await page.evaluate(() => { window.testDevices.permission = 'allow'; });
  await load(page);
  await transcribe(page);
  await emit(page, ikhlas.split(' ').slice(4).join(' '));
  await expect(page.locator('#word-summary')).toContainText('No clear whole-word skips');
  await expect(page.locator('#reference-verses p')).toHaveCount(4);
});

test('source reference is rendered verbatim as text, never interpreted as HTML', async ({ page }) => {
  const source = '  gold <img src=x onerror="window.injected=true"> literal&amp;source  ';
  await page.evaluate(source => { window.testDevices.records[9].text_uthmani = source; }, source);
  await load(page);
  await transcribe(page);
  await emit(page, 'unrecognised words');
  await page.getByText('Reference for your own review', { exact: true }).click();
  expect(await page.locator('#reference-verses p').allTextContents()).toContain(source);
  await expect(page.locator('#reference-verses img')).toHaveCount(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  await expect(page.locator('#word-summary')).toContainText('Word check: unsure');
});

test('empty recognition and malformed reference produce no word diagnosis', async ({ page }) => {
  await load(page);
  await transcribe(page);
  await emit(page, ' ');
  await expect(page.locator('#status')).toContainText('No words were recognized');
  await expect(page.locator('#result-panel')).toBeHidden();
  await expect(page.locator('#word-findings')).toBeEmpty();
  await page.reload();
  await page.evaluate(() => { window.testDevices.records.pop(); });
  await page.getByRole('button', { name: 'Load speech test' }).click();
  await expect(page.locator('#status')).toContainText('reference could not be verified');
  await expect(page.getByRole('button', { name: 'Start reciting' })).toBeHidden();
  expect(await page.evaluate(() => window.testDevices.requests)).toBe(0);
});
