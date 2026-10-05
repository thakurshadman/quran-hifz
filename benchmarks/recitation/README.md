# Reproduce the Al-Ikhlas model comparison

For the larger, three-dataset comparison, see [results](PUBLIC-RESULTS.md) and
[repeatable test steps](PUBLIC-DATASETS.md).

The follow-up [FastConformer comparison](FASTCONFORMER.md) and
[Qwen3-ASR comparison](QWEN.md) use Tilawi as the baseline.

The [repeated-audio test](REPETITION.md) checks whether Tilawi and Mohammed’s model keep two copies
when exactly the same recording is played twice.

The [Muaalem sound-level test](MUAALEM.md) inspects raw phoneme predictions.
The [leaderboard research](PHONEME-MODELS.md) covers RAM, Utokyo and SQZ_ww.

This ASR-004 experiment compares four recognizers using the **same audio**,
fixed model files, the same reference scope and explicit scoring rules. It is
an exploratory batch-transcription test, not a complete benchmark of students,
mistake detection, live latency or tajwīd. The app's architecture is not selected
by these scripts. Related: [ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7),
[requirements](../../docs/requirements/NFR-001.md), [pilot privacy](../../docs/security/SEC-001.md).

## What the original comparison did

1. Used one private 16.8-second, 48 kHz stereo PCM16 WAV.
2. FFmpeg converted it to mono float32 audio at 16 kHz. No noise removal,
   loudness adjustment, trimming or expected-text prompt was applied.
3. Ran Tilawi, Whisper Tiny q8, Tarteel Whisper Base and Qur’an Whisper Turbo
   locally on CPU, with two configured compute threads. The audio was not sent
   to any inference service.
4. Compared each raw transcription with the 15 words of Al-Ikhlas, excluding
   the basmala, after the normalization described below.
5. Counted substitutions, deletions and insertions using minimum word edit
   distance. Timed one inference per model after loading it.

[Original results and limitations](RESULTS.md) distinguish this historical run
from fresh runs using the packaged harness. No claim that the original runtime
was a browser test or a repeated statistical benchmark is made.

## Install

The recorded environment was Linux x86-64, Python **3.12.14**, Node **24.19.0**,
FFmpeg **7.1.5-0+deb13u1** and an AMD EPYC 9V74 virtual CPU (three CPUs visible).
Use about 8 GB available RAM and allow several GB for models and dependencies.
Other platforms can differ in available wheels, numerical output and speed.

From the repository root, with FFmpeg and these runtimes already installed:

```sh
python3.12 -m venv /tmp/quran-benchmark-venv
/tmp/quran-benchmark-venv/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.8.0+cpu'
/tmp/quran-benchmark-venv/bin/python -m pip install -r benchmarks/recitation/requirements-linux-cpu.lock
npm ci --ignore-scripts --prefix experiments/ikhlas-test
```

The Python lock records every installed distribution in the original comparison;
the existing experiment's `package-lock.json` locks Node dependencies. The CPU
PyTorch wheel uses the PyTorch index; other pinned packages use PyPI. This is a
version-pinned Linux environment, not a container image or a hash-locked Python
supply chain. Model assets themselves are verified by SHA-256 before inference.

## Download models, then run offline

Keep your audio, cache and reports **outside the repository**. Downloading public
model files uses Hugging Face; the subsequent inference uses local model files.
No cloud account or inference API key is required for these four candidates.

```sh
/tmp/quran-benchmark-venv/bin/python benchmarks/recitation/benchmark.py download \
  --cache /tmp/quran-models --models tilawi tiny tarteel quran-turbo

/tmp/quran-benchmark-venv/bin/python benchmarks/recitation/benchmark.py run \
  --audio /path/to/your/recitation.wav \
  --cache /tmp/quran-models --models tilawi tiny tarteel quran-turbo \
  --basmala exclude --warmups 0 --repeats 1 \
  --output /tmp/quran-result.json
```

Use `--basmala include` only when the intended recording includes it. The choice
is a declared reference scope; the harness does not strip unexpected spoken
words from a hypothesis to improve its score. Input is limited to 30 seconds.
Use a new output filename for each run. Reports are local and should be reviewed
before sharing: even a recording's hash can identify a private sample.

For a more useful timing sample, change `--warmups 1 --repeats 5`. Keep the same
device and configuration across models. Warmups are excluded; every measured
run remains visible. Medians from five runs are still not a reliable p95 or a
measure of phone/browser speed. No single threshold declares a model the winner.

Anyone can reproduce the **method** on their own authorized recording. They
cannot independently reproduce the exact original word counts without the
original private recording, which is deliberately not distributed. To establish
a public accuracy benchmark later, select a redistributable corpus with verified
rights and a human-checked transcript; no such corpus is bundled here.

## Models and verification

[models.json](models.json) records immutable Hugging Face revisions, file sizes
and SHA-256 digests for weights, tokenizer/config files and reference assets.
Cached and freshly downloaded files must match; a mismatch is an error, never
a reason to silently use another model. Updating pins requires a reviewed change.

| Candidate | Model repository | Runtime / decoding | License |
| --- | --- | --- | --- |
| Tilawi | `muhdur/tilawi-fastconformer-quran` | Mixed-quantized ONNX, greedy CTC, blank ID 1024 | CC-BY-4.0 |
| Tiny baseline | `Xenova/whisper-tiny` | Quantized q8, Transformers.js, Arabic transcription | Apache-2.0 |
| Tarteel Base | `tarteel-ai/whisper-base-ar-quran` | PyTorch, greedy Arabic transcription | Apache-2.0 |
| Qur’an Turbo | `naazimsnh02/whisper-large-v3-turbo-ar-quran` | PyTorch, greedy Arabic transcription | Apache-2.0 |

Whisper uses no sampling, one beam and a maximum of 128 new tokens. No decoder
receives the expected surah as a text prompt. Tilawi uses its raw CTC output,
without canonical-text matching or snapping. `Muno459/fastconformer-quran` is a
different model requiring manual access approval; it is not tested by this harness.

Dependencies reuse Transformers.js/ONNX Runtime from the prototype, adding the
original Python Transformers **4.57.6** and PyTorch **2.8.0 CPU** environment for
the two models without the same ONNX format. These are mature local-inference
libraries (Apache-2.0/BSD-style licensing) with larger disk/RAM costs. An all-ONNX
comparison would reduce runtime differences but require conversions, creating a
different experiment. No paid service or production dependency is introduced.
FFmpeg is an external executable with build-dependent LGPL/GPL licensing; record
its actual version/configuration when comparing runs. The reference's Tanzil
notice travels in the cache. Model licenses are listed above and should be
checked at the pinned upstream revisions before redistribution; this harness
does not bundle each model's license document. Weights/text are not redistributed
in this repository.

## Scoring and reference text

The frozen Tilawi reference asset is derived from Tanzil; its accompanying
`TANZIL-NOTICE.txt` is downloaded and its hash pinned. No Qur’an text is generated
or rewritten. Only derived comparison tokens are normalized; the source is intact.

The source prefixes verse 112:1 with the basmala. The scorer removes that prefix
**once** to obtain the 15-word surah and adds it back only for the explicitly
selected 19-word scope. It validates the four verse records and expected count.

Normalization removes vowel/recitation marks (including superscript waw/yeh),
tatweel and punctuation, and unifies alef variants. Other hamza forms remain
distinct. It does not prove vowel
or pronunciation correctness. Normalization is an experimental comparison rule,
not an approved application-grading rule or a substitute for qualified review.

Minimum edit distance reports `substitutions + deletions + insertions`, divided
by reference-word count for a percentage. Tie-breaking is deterministic. These
are **differences from the intended passage**, not proven mistakes in a user's
recitation. Without a human-verified transcript of the actual speech, the report
must not be called a general ASR word-error-rate result. A recognizer can output
the expected words while hiding a real spoken omission or substitution.

## Timing, privacy and tests

Each model loads once per process; its load time is separate. To preserve the
original clocks, Tilawi times only ONNX `session.run` (embedded preprocessing
and inference, excluding the small CTC text-decoding loop). Tiny times its entire
pipeline call. Python Whisper times feature extraction, generation and text
decoding. Each report records this `timer_scope`. All exclude audio-file
conversion, model downloads and loading. These different timer scopes, native
runtimes and numeric precisions limit speed comparisons; this is not a controlled
architecture speed comparison. Reports include the input hash, preprocessing,
reference scope, model pins, runtime/device metadata, repeat counts and timings.

Audio is decoded into a restrictive temporary directory and removed after the
run. Worker transcripts pass only through local subprocess pipes for scoring;
they are neither printed nor saved in reports. No audio or transcript artifacts
are uploaded by CI. Temporary original transcripts from the exploratory run
were deleted; its aggregate counts and notes are preserved in RESULTS.md.

Run the lightweight, offline regression suite:

```sh
python -m unittest discover -s benchmarks/recitation/tests -p 'test_*.py' -v
```

CI tests scoring, reference-scope mistakes, asset integrity, privacy boundaries
and orchestration using synthetic data/doubles. It does not download gigabytes
of models or pretend those tests establish recognition accuracy. Real-model
validation is run separately and identified in PR evidence. This work does not
close ASR-001/002/003/004 or satisfy M0's representative-data/error-detection gates.
