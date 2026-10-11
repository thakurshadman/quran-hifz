# Qur’an Hifz personal practice app

Choose a Juz 29 surah, Al-Fatiha or Al-Ikhlas, recite, and inspect **possible whole-word skips or
repeated verses**. Pronunciation always says **unsure**. No flags does not mean
that a recitation is correct. Recognition can miss mistakes or invent words.

This personal app uses an experimental recognizer under [ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7)
and [ASR-007 #10](https://github.com/thakurshadman/quran-hifz/issues/10), not a
production model decision or an accuracy claim. Rust/WASM owns the practice logic under [ADR-001](../../docs/architecture/adr/ADR-001-rust-practice-core.md).
The full original MVP is not complete: authentic audio prompts, live partial
feedback, difficulty levels and validated recognition still need work.

## Use

Open the page over HTTPS, choose a surah and load the model. Under “Choose verses”
select a range of up to 100 words, or pick a random range of 1–3 verses from this
surah or all of Juz 29. Random choice is weighted by eligible starting verses,
using the browser's random seed; the same seed and scope reproduce a choice.
The last range in a surah can contain fewer verses. Next passage picks again.
The optional cue shows the first original verse and hides before capture.

Choose whether to include the opening basmala when starting from verse 1.
Al-Fatiha verse 1 always includes it. Random ranges outside Al-Fatiha omit it.
The current visit counts completed attempts in memory only; nothing is saved.
Press Start, allow microphone access, then recite for up to 60 seconds and Stop.
The microphone turns off before recognition runs. Clear removes the result;
Cancel, changing passage during an attempt, or hiding the page discards it.

The first load downloads about 106 MB including model, reference and runtime.
These public files may be cached. Slow phones may take longer or run out of
memory. iPhone, Android and desktop still need physical-device testing.

## How the comparison works

Tilawi produces a raw transcription without receiving the expected passage as
a prompt. A separate comparison looks for a single best word alignment.
For example: expected `A B C D`, heard `A B D` → **possible skip of word 3**.
These are guesses about recognized words, not proof of what someone said.

- At least 70% of reference words must match. This provisional threshold is not
  calibrated. Substitutions, extra words or tied alignments make the entire
  result unsure. This misses some real skips and repeats when other words are unclear.
- A repeated verse must match every word of that verse. Repeated words and
  pronunciation errors are not graded. A missing first or last reference word
  makes the passage incomplete and unsure.
- Up to two closing words can remain unassessed only if neither occurs anywhere
  in the selected reference. They are disclosed, not counted as correct.
- Alignment costs are 0 for a match and 1 for a skip, extra word, substitution,
  or complete verse repeat. Input limits are 100 reference words, 200 recognized
  words and 5,000 transcript characters. This is batch feedback after Stop.

## Source text and licenses

[tilawi-pins.json](tilawi-pins.json) freezes Tilawi model revision
`e9448a0e84f3adb64c28b7a8db501dd8e0e59a84`, file sizes and SHA-256 hashes, matching
[the benchmark manifest](../../benchmarks/recitation/models.json). Model, vocabulary,
reference and notice bytes are verified before use. Tilawi is CC-BY-4.0:
[model source](https://huggingface.co/muhdur/tilawi-fastconformer-quran/tree/e9448a0e84f3adb64c28b7a8db501dd8e0e59a84).

The pinned `quran.json` supplies the Tanzil Uthmani reference. Its original strings
are displayed unchanged; the page links the pinned Tanzil notice. Comparison
copies remove marks and tatweel, unify alef variants, and allow a superscript-alif
expanded spelling. These transformations never replace source display text.
Each supported source surah outside Al-Fatiha has verse 1 containing the four-word basmala: comparison separates
it according to the checkbox, while source display keeps the original intact.
Word positions count source words, including that prefix. Standalone pause or
section marks are not words; they remain in the untouched display text.

Technical source checks do not replace a qualified Qur'an-content review. That
review remains open for acceptance of this reference and normalization; do not claim that agent reviews
replace it. The owner has authorized completing the personal app autonomously.

## Run and verify

Use Node 24.19.0, Rust 1.90.0 and the committed lockfiles. From the repository root:

```sh
rustup show
cargo install wasm-bindgen-cli --version 0.2.104 --locked
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
```

Then build the browser app (build/dev/test compile Rust automatically):

```sh
cd experiments/ikhlas-test
npm ci --ignore-scripts
npm run dev -- --port 4173
```

Localhost supports microphones. Phones accessing a LAN address need HTTPS.
Build with `npm run build`; serve only `dist/`, never the repository root.

```sh
npm test
npx playwright install chromium
npm run test:browser
npm run build
npm audit
```

Native Rust tests and the original JavaScript tests (now calling real Rust/WASM)
use synthetic words to check skips, repeats, ambiguous matches and
bounds. Browser tests mock recognition to check controls, cleanup, stale results,
source display and failures. They do not measure speech accuracy.

With the dev server running, `node scripts/model-smoke.js` loads the real model
and transcribes synthetic silence. For the built page, serve `dist/` at
127.0.0.1:4174 and run `node scripts/production-smoke.js`. That check uses synthetic
microphone audio and rejects non-GET/HEAD requests. Its screenshot is only for
local debugging; never capture a person's transcript without agreement.

Accuracy testing belongs in the separate [recitation benchmark](../../benchmarks/recitation/README.md).
Do not commit private recordings, transcripts or results. Browser capture uses
simple linear resampling to 16 kHz; a proper anti-alias filter remains a follow-up.
Native benchmark results do not establish browser or phone accuracy or latency.

To verify the pinned public reference locally, pass the downloaded `quran.json`:

```sh
node scripts/check-reference.js /path/to/quran.json
```

## Privacy and dependencies

Audio stays in a bounded memory buffer, then runs through a local WASM worker.
No audio or transcript is uploaded, logged or saved to browser storage. Buffers
are dropped or zeroed after use; this is not a forensic memory-erasure promise.
Hugging Face sees public model-download requests, including IP address; hosting
sees page requests. There is no remote speech fallback or paid inference service.

- Rust core: `wasm-bindgen` **0.2.104**, `serde` **1.0.228**, `serde_json`
  **1.0.145**, `unicode-normalization` **0.1.24**, MIT/Apache-2.0. These maintained
  libraries avoid hand-written Unicode tables and unsafe browser ABI code.
  Cargo.lock pins transitives. The CLI is build-only; no Rust server is needed.
  Native/WASM tests cover the shared implementation. No RustSec audit is claimed.
- `onnxruntime-web` **1.31.0-dev.20260914-8d85527a0**, MIT, is now a direct
  dependency at the same already-locked version. Its maintained upstream supports
  the existing ONNX model without a custom inference engine. Single-thread WASM
  avoids WebGPU and cross-origin isolation requirements. The prerelease version
  remains a compatibility risk; runtime and license are served locally.
- `@huggingface/transformers` **4.3.0**, Apache-2.0, remains for benchmark tooling;
  the browser worker no longer imports it. Direct ONNX inference replaces the
  previous Whisper Tiny path to test the user's selected Tilawi baseline.
- Vite **8.3.2**, MIT, builds the page. Playwright **1.63.0**, Apache-2.0, tests it.

The lockfile pins exact versions. Audit dependency updates and rerun the browser
and real-model checks before changing them. There are no new inference fees;
device resources, hosting and download bandwidth still have costs. Browser-native
speech and remote services remain alternatives, with different privacy and setup
needs. Rust/WASM is accepted for this personal app; the eventual production stack
and recognition model still need validation.

Revert this change to restore the earlier isolated experiment. This work does
not close ASR-004/007, qualify pronunciation scoring, or meet the proposed NFR
accuracy and latency targets.
