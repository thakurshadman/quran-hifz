import * as ort from 'onnxruntime-web/wasm';
import { checkedAsset, decodeCTC } from './tilawi.js';
ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
const runtime = new URL('../runtime/', self.location.href);
ort.env.wasm.wasmPaths = { mjs: new URL('ort-wasm-simd-threaded.mjs', runtime).href, wasm: new URL('ort-wasm-simd-threaded.wasm', runtime).href };
let session, vocab, busy = false;
self.onmessage = async ({ data }) => {
  if (busy) return;
  busy = true;
  try {
    if (data.type === 'load') {
      self.postMessage({ type: 'progress', message: 'Downloading Tilawi and checking the reference. The microphone is off.' });
      const [weights, vocabulary, reference] = await Promise.all([
        checkedAsset('fastconformer_full_mixed.onnx'), checkedAsset('vocab.json'), checkedAsset('quran.json'), checkedAsset('TANZIL-NOTICE.txt'),
      ]);
      vocab = JSON.parse(new TextDecoder().decode(vocabulary));
      session = await ort.InferenceSession.create(weights, { executionProviders: ['wasm'], logSeverityLevel: 3 });
      self.postMessage({ type: 'ready', records: JSON.parse(new TextDecoder().decode(reference)) });
    } else if (data.type === 'transcribe' && session) {
      if (!(data.audio instanceof Float32Array) || data.audio.length < 1600 || data.audio.length > 960000 || !data.audio.every(Number.isFinite)) throw new Error('Invalid input');
      const started = performance.now();
      const result = await session.run({ audio_signal: new ort.Tensor('float32', data.audio, [1, data.audio.length]),
        length: new ort.Tensor('int64', BigInt64Array.from([BigInt(data.audio.length)]), [1]) });
      const text = decodeCTC(result[session.outputNames[0]], vocab);
      self.postMessage({ type: 'result', text, elapsedMs: performance.now() - started });
    } else throw new Error('Not ready');
  } catch {
    self.postMessage({ type: 'error', message: 'The word test could not finish. Try another browser or a shorter recording.' });
  } finally {
    if (data.audio instanceof Float32Array) data.audio.fill(0);
    busy = false;
  }
};
