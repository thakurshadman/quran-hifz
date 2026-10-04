import { env, pipeline } from '@huggingface/transformers';

// Only model assets cross the network. Audio and results stay in this worker
// and the page's memory; there is no transcription endpoint or upload fallback.
env.allowLocalModels = false;
env.useBrowserCache = true;
env.backends.onnx.wasm.numThreads = 1;
env.backends.onnx.wasm.proxy = false;
const runtime = new URL('../runtime/', self.location.href);
env.backends.onnx.wasm.wasmPaths = {
  mjs: new URL('ort-wasm-simd-threaded.mjs', runtime).href,
  wasm: new URL('ort-wasm-simd-threaded.wasm', runtime).href,
};

let recognizer;
let busy = false;

self.onmessage = async ({ data }) => {
  if (busy) return;
  busy = true;
  try {
    if (data.type === 'load') {
      self.postMessage({ type: 'progress', message: 'Downloading the speech model. The first load may take a few minutes.' });
      recognizer = await pipeline('automatic-speech-recognition', 'Xenova/whisper-tiny', {
        revision: '5332fcc35e32a33b86612b9a57a89be7906102b1',
        device: 'wasm',
        dtype: 'q8',
      });
      self.postMessage({ type: 'ready' });
    } else if (data.type === 'transcribe' && recognizer) {
      if (!(data.audio instanceof Float32Array) || data.audio.length < 1600 || data.audio.length > 480000) {
        throw new Error('Invalid audio length');
      }
      const started = performance.now();
      const result = await recognizer(data.audio, {
        language: 'arabic', task: 'transcribe', return_timestamps: false,
        max_new_tokens: 128,
      });
      // Do not prompt with the expected passage: that could conceal omissions.
      data.audio.fill(0);
      self.postMessage({ type: 'result', text: result.text, elapsedMs: performance.now() - started });
    } else {
      throw new Error('Speech model not ready');
    }
  } catch {
    // Raw exceptions may contain payloads; send only a fixed safe message.
    if (data.audio instanceof Float32Array) data.audio.fill(0);
    self.postMessage({ type: 'error', message: 'The speech test could not finish. Try again, or try another browser or device.' });
  } finally {
    busy = false;
  }
};
