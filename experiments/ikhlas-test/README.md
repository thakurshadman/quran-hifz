# Al-Ikhlas speech experiment

Working prototype for the owner's requested first test: recite Surah 112 from
memory, stop, and inspect a tentative Arabic transcription. This is an isolated
ASR-007 experiment, not the MVP, a representative benchmark, or a selected
production architecture. Al-Ikhlas is the user's explicit test passage; the
product's Juz 29 scope is unchanged. Related issue: [ASR-007 #10](https://github.com/thakurshadman/quran-hifz/issues/10).

## Use

Open the hosted page over HTTPS. Load the speech test, then press Start and allow
microphone access. Recite for up to 30 seconds and press Stop. The microphone
turns off before the AI runs. Cancel discards the attempt; Clear removes the
transcript. Leaving or hiding the page clears the attempt and unloads the model.

The first load downloads roughly 41 MB of model weights plus 14 MB of runtime
and supporting files. Downloads may be cached. A slow phone may need more time
or fail for lack of memory. Safari/iPhone, Chrome/Android and desktop are target
devices, not a claim that physical devices have all passed testing.

There is no reference Qur’an text, generated prompt, word comparison, correctness
score, tajwīd assessment, or live word feedback. Displayed ASR output is explicitly
unverified and can omit or invent words. Processing time measures the batch
inference after Stop, not acoustic-word-to-feedback latency or M0 success.

## Run locally

Use Node 24.19.0 and the committed lockfile:

```sh
cd experiments/ikhlas-test
npm ci --ignore-scripts
npm run dev -- --port 4173
```

Localhost supports microphone access. A phone visiting an ordinary LAN HTTP URL
will need HTTPS instead. Production output comes from `npm run build` in `dist/`.
Only built public assets belong in hosting; do not serve the repository root.

## Privacy and dependencies

Audio goes from microphone to a bounded in-memory AudioWorklet buffer, then to a
local worker running Whisper. Audio is never uploaded or written to browser
storage, server files, logs or analytics. The app drops/zeros its buffers after
processing, cancellation and page lifecycle cleanup; this is not a claim of
forensic erasure from a browser's memory. Transcripts remain visible until cleared.
Only model assets use browser caching. Hugging Face receives model-download
requests, including IP address; normal site hosting also sees page requests.
There is no fallback to a remote recognizer and no paid API key is needed.

- `@huggingface/transformers` **4.3.0**, Apache-2.0: maintained browser inference
  wrapper. It avoids writing a tokenizer/decoder and binds ONNX Runtime Web.
- `onnxruntime-web` **1.31.0-dev.20260914-8d85527a0**, MIT: upstream version locked
  by Transformers. Single-thread WASM avoids cross-origin isolation and WebGPU
  requirements. The runtime and its license are served locally; its prerelease
  identifier is a compatibility risk to recheck before production.
- `Xenova/whisper-tiny`, Apache-2.0 model card, frozen revision
  `5332fcc35e32a33b86612b9a57a89be7906102b1`, quantized multilingual weights:
  [model source](https://huggingface.co/Xenova/whisper-tiny/tree/5332fcc35e32a33b86612b9a57a89be7906102b1).
  Chosen as a small baseline, not for established Qur’an accuracy. No expected
  passage is supplied as a decoding prompt, which could hide omissions.
- Vite **8.3.2**, MIT, build/dev only: bundles static assets and workers.
- Playwright **1.63.0**, Apache-2.0, test only: tests browser controls and failures.

Exact transitive versions/integrities are in `package-lock.json`. Browser code
does not import Node-only image/native-inference packages. Model revision pins
are immutable content references; an integrity manifest for a production model
distribution remains future work. `npm audit` was clean at initial verification;
rerun it for dependency changes. No app-store costs or inference service charges;
device resources, hosting and model-download bandwidth still matter.

Online Azure/OpenAI recognition remains an alternative for weaker devices after
account setup and actual audio-policy review. Browser-native speech recognition
was excluded here because remote routing/retention varies by browser. No runtime
or framework is being accepted for the eventual product by this experiment.

## Validation and limits

```sh
npm test
npx playwright install chromium
npm run test:browser
npm run build
npm audit
```

Initial local verification: four unit/worklet tests and 26 Chromium browser
checks passed. The built page also passed a full integration smoke with the real
model and real browser microphone APIs fed synthetic audio, with no failed
network requests and no POST/upload requests. Real-model batch inference on
one second of synthetic silence took about 1.9 seconds on this host; that is not
a phone measurement or recognition-accuracy result. WebKit could not run here
because required system libraries were unavailable.

`scripts/model-smoke.js` runs against the dev server on localhost:4173 and loads
the actual model, then transcribes synthetic silence. It proves the inference
path executes; it supplies no recitation accuracy evidence. Browser lifecycle
tests explicitly mock permissions/audio/recognition to exercise failures. These
are separate from real-model checks and eventual physical-device trials.

For the production integration check, serve `dist/` at 127.0.0.1:4174 and run
`node scripts/production-smoke.js`. It uses synthetic browser audio and fails on
any non-GET/HEAD request. Its screenshot is a local debugging artifact only;
never adapt that capture step to record a person's transcript without agreement.

Capture currently uses simple linear downsampling to 16 kHz without an
anti-alias filter. Treat this as a prototype limitation when interpreting model
quality; compare a proper band-limited resampler before any accuracy claim.

Human testing still needs an actual recitation on iPhone, Android and desktop.
Record only non-identifying observations such as browser/device, elapsed time
and whether the displayed words seem plausible. Do not commit recordings or
transcripts. This experiment does not close ASR-004 or ASR-007 or ratify NFR
accuracy/latency thresholds. Remove this directory to revert the prototype.
