# FastConformer versus Tilawi

The owner selected Tilawi as our comparison baseline and asked to test
[Mohammed’s FastConformer](https://huggingface.co/mohammed/fastconformer-quran-ar)
against it. Both belong to the FastConformer family, but they have different
training, model files and decoding methods.

This experiment supports [ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7).
It does not change the app or select its production architecture.

## Results

**Mohammed’s FastConformer matched more clips in the error dataset and RetaSy;
Tilawi matched more in OpenSLR.** Keep Tilawi as the reference baseline and
include Mohammed’s model in the next test of known skipped or changed words.
This small comparison does not establish a general winner.

All **240 transcriptions completed**, with no processing failures in the full
run. Tilawi’s word counts and exact matches reproduced its previous results
on every clip. An exact match means agreement with the supplied passage after
normalization, not proof that the recitation was correct.

| Model | OpenSLR (50) | Error dataset (50) | RetaSy (20) |
| --- | ---: | ---: | ---: |
| Tilawi | 47/50 | 29/50 | 6/20 |
| Mohammed FastConformer | 43/50 | 36/50 | 7/20 |

Word differences count substituted, missing and added words, divided by total
reference words. Lower is closer to the supplied text. These are not verified
recognition error rates or learner mistake-detection scores.

| Model | OpenSLR (664 words) | Error dataset (249 words) | RetaSy (88 words) |
| --- | ---: | ---: | ---: |
| Tilawi | 3.01% | 37.35% | 43.18% |
| Mohammed FastConformer | 3.77% | 33.73% | 31.82% |

The source-label groups show exact text matches, not validated error detection:

| Model | Error tags (20) | No error tags (30) | RetaSy “correct” (10) | RetaSy “in_correct” (10) |
| --- | ---: | ---: | ---: | ---: |
| Tilawi | 10/20 | 19/30 | 5/10 | 1/10 |
| Mohammed FastConformer | 11/20 | 25/30 | 6/10 | 1/10 |

Median processing seconds per clip:

| Model | OpenSLR | Error dataset | RetaSy |
| --- | ---: | ---: | ---: |
| Tilawi | 0.681 | 0.175 | 0.150 |
| Mohammed FastConformer | 0.646 | 0.234 | 0.238 |

Tilawi’s timer covers ONNX inference before CTC text decoding. NeMo’s covers
feature processing, inference and RNNT text decoding through its transcription
call. Downloads, loading and common audio conversion are excluded. Different
timer scopes and runtimes limit speed comparisons. This is not a phone test.

### Recorded evidence

The [complete report](published/fastconformer-120.json) includes every clip’s
counts, per-source and per-label totals, timings, model versions, settings and
hashes. It contains no audio, reference text, transcriptions or speaker IDs.

- Run date: 2026-10-04; clean executing commit
  `6897e7aaa7debc7df829493d7bfc25fe97acfe1b`.
- Machine: Linux x86-64, AMD EPYC 9V74 virtual CPU, three logical CPUs visible,
  about 10 GB RAM; two compute threads and one inter-op thread.
- Native CPU inference: Tilawi mixed-quantized ONNX; Mohammed float32 NeMo.
  Both use full-clip audio. Neither uses a passage prompt or canonical matching.
- All 120 audio files matched their frozen hashes; the 20 RetaSy files were
  freshly prepared from the existing lock. No samples were replaced.
- Temporary RetaSy audio and text manifests were deleted after independent
  report validation.
- 110 automated benchmark tests and 30 documentation tests passed. These check
  the harness; the 240 real transcriptions were run locally, outside CI.

## Comparison rules

- Use the same frozen 120 recordings from the [public dataset test](PUBLIC-DATASETS.md):
  50 OpenSLR, 50 error-dataset and 20 RetaSy clips. No new sample selection.
- Run both models again on the same decoded mono, 16 kHz float32 audio, with
  two CPU compute threads. Load each model once; run each clip once, without warmup.
- Keep the existing text normalization and word-difference scorer unchanged.
  Give neither model the reference text, a passage prompt or canonical matching.
- Report the three datasets separately, including the source-label groups.
  Keep raw audio, references and transcripts out of published reports.
- Delete temporary RetaSy audio and local text manifests after validation, as
  in the previous comparison. Its formal reuse license remains unresolved.

The new checkpoint was chosen before inference: the final `phase3_full` file
named by the author’s advertised 0.14% validation result, at revision
`60973918b40c5fcdc0e93310c13a4a4661525142`. That is the author’s claim on their
EveryAyah validation data, not our result or evidence that it beats Tilawi.
The download is 459,243,520 bytes, versus Tilawi’s 88,307,366-byte quantized ONNX
model. Download size alone does not establish memory use or phone speed.

An initial one-clip smoke test checks runtime compatibility only. Full comparison
runs start new processes, with the samples and decoding fixed before scores
are inspected.

## Runtime and dependency choice

Mohammed’s released checkpoint uses NVIDIA NeMo. We use its native CPU runtime
in a separate Python environment to test the released model directly. Converting
it to ONNX first would add an unvalidated conversion and change the experiment.
NeMo, PyTorch and their supporting packages are research-only dependencies;
they are not added to the app. No paid inference service is used.

The model card declares CC-BY-4.0 for the checkpoint; Tilawi also declares
CC-BY-4.0. NeMo is Apache-2.0 and PyTorch uses a BSD-style license. NeMo is a
maintained NVIDIA speech toolkit, but brings substantially more dependencies
than our existing ONNX adapter. Exact installed versions are recorded with this
test. Version pins and hashes aid reproduction; they are not a complete security
or upstream training-data rights audit. The research environment also includes
GPL-2.0-or-later `Levenshtein` and LGPL dependencies such as `num2words` and
`soxr`. We publish version pins and our harness, not those packages or a bundled
application; any future distribution needs its own license review.

The checkpoint must pass its pinned size and SHA-256 check before loading.
Archive members and configuration are checked, and checkpoint tensors use
restricted weights-only loading. Inference uses local assets, with library
output captured so reference text and transcriptions are not logged.

## Repeat the comparison

Use Linux x86-64 with Python 3.12.14, Node 24.19.0, FFmpeg and a C/C++ compiler.
Allow about 3 GB for the Python environment and model, plus space for downloads
and temporary files. Our machine had about 10 GB RAM. Keep model caches,
recordings and reports outside Git checkouts.

```sh
python3.12 -m venv /tmp/fastconformer-env
/tmp/fastconformer-env/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.8.0+cpu' 'torchaudio==2.8.0+cpu'
CC=gcc CXX=g++ /tmp/fastconformer-env/bin/python -m pip install -r benchmarks/recitation/fastconformer-requirements-linux-cpu.lock
/tmp/fastconformer-env/bin/python -m pip check
npm ci --ignore-scripts --prefix experiments/ikhlas-test

/tmp/fastconformer-env/bin/python benchmarks/recitation/fastconformer.py download --cache /tmp/fastconformer-models
/tmp/fastconformer-env/bin/python benchmarks/recitation/prepare_datasets.py --destination /tmp/fastconformer-public
/tmp/fastconformer-env/bin/python benchmarks/recitation/prepare_retasy.py --destination /tmp/fastconformer-retasy

/tmp/fastconformer-env/bin/python benchmarks/recitation/fastconformer.py run \
  --manifest /tmp/fastconformer-public/openslr132.json \
  --manifest /tmp/fastconformer-public/recitation_errors.json \
  --manifest /tmp/fastconformer-retasy/retasy.json \
  --cache /tmp/fastconformer-models \
  --output /tmp/fastconformer-comparison.json
```

Use new sample directories and an output filename that does not exist. The
preparation scripts check the original frozen audio/reference hashes. Inference
runs offline after preparation. Delete the temporary RetaSy directory after
validating the report, including partial downloads after any failure.

NeMo 2.5.3 runs with PyTorch/torchaudio 2.8.0 CPU and NumPy 1.26.4. The checkpoint
records NeMo 2.0.0rc1; restoration into 2.5.3 uses strict matching of weights.
The complete installed package versions are frozen, but build tools and package
hashes are not locked. `texterrors` builds a small C++ extension; explicit
`CC=gcc CXX=g++` avoids an unavailable compiler selected by some Python builds.
No custom edits to installed libraries are required.

## Limits

These are differences from the dataset’s expected passage, not verified speech
error rates or learner scores. A model can fill in a skipped word and match the
reference while hiding a mistake. Source spelling differences, the RetaSy
opening-invocation reference, unverified labels and possible training overlap
remain as described in the [earlier results](PUBLIC-RESULTS.md).

Mohammed’s model uses an RNNT decoder; Tilawi uses greedy CTC. The models also
use different runtimes and numerical formats. Any timing comparison describes
these complete configurations, not the architecture alone. Native CPU timings
do not establish iPhone, Android, browser or live feedback performance.

No qualified content review or M0 acceptance is claimed.
