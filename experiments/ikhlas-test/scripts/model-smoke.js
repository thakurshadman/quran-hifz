import { chromium } from '@playwright/test';

// Real-model infrastructure check only; synthetic silence proves no accuracy.
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const failures = [];
  page.on('requestfailed', request => failures.push({ url: request.url().split('?')[0], error: request.failure()?.errorText }));
  await page.goto('http://localhost:4173');
  const result = await page.evaluate(async () => {
    const worker = new Worker('/recognizer-worker.js', { type: 'module' });
    return new Promise((resolve, reject) => {
      const started = performance.now();
      const timer = setTimeout(() => { worker.terminate(); reject(new Error('model smoke timed out')); }, 180000);
      worker.onerror = () => { clearTimeout(timer); worker.terminate(); reject(new Error('worker failed')); };
      worker.onmessage = ({ data }) => {
        if (data.type === 'ready') worker.postMessage({ type: 'transcribe', audio: new Float32Array(16000) });
        if (data.type === 'result' || data.type === 'error') {
          clearTimeout(timer); worker.terminate();
          resolve({ type: data.type, elapsedMs: performance.now() - started, inferenceMs: data.elapsedMs });
        }
      };
      worker.postMessage({ type: 'load' });
    });
  });
  console.log(JSON.stringify({ result, failures }));
  if (result.type !== 'result') process.exitCode = 1;
} finally { await browser.close(); }
