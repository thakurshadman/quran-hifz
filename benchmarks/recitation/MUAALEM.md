# Testing sounds with Muaalem

A word recognizer can fill in a sound that someone skipped. This experiment
checks Muaalem's raw sound predictions instead. Think of checking the letters
someone said, rather than asking a spellchecker to finish the word.

This is exploratory work for [ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7).
It does not choose the app's model or establish pronunciation accuracy.

## Repeat the method

Use your own authorized recordings: one intended correct version and versions
with a known missing sound or repetition. Write down the intended changes
before running the model. A filename alone is not verified ground truth.

The runner accepts one to ten local recordings, each up to 60 seconds. It
converts the full audio to mono, 16 kHz float32 samples with FFmpeg. It does not
trim silence, remove noise or supply an expected verse. Longer input is rejected.

Use Linux x86-64, Python 3.12.14 and FFmpeg. The existing
[Qwen runtime lock](qwen-requirements-linux-cpu.lock) is reused unchanged:
PyTorch 2.8.0 CPU, Transformers 4.57.6 and NumPy 2.5.3. This avoids changing
dependencies between experiments; the Qwen model itself is not loaded.
Allow several GB for the environment and the 2.42 GB model. Use disk-backed
storage for the environment, cache and temporary files.

From the repository root:

```sh
python3.12 -m venv /var/tmp/muaalem-env
/var/tmp/muaalem-env/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.8.0+cpu'
/var/tmp/muaalem-env/bin/python -m pip install -r benchmarks/recitation/qwen-requirements-linux-cpu.lock
/var/tmp/muaalem-env/bin/python -m pip check

/var/tmp/muaalem-env/bin/python benchmarks/recitation/muaalem.py download \
  --cache /var/tmp/muaalem-model

mkdir -p /var/tmp/muaalem-tmp
TMPDIR=/var/tmp/muaalem-tmp /var/tmp/muaalem-env/bin/python benchmarks/recitation/muaalem.py run \
  --cache /var/tmp/muaalem-model \
  --audio /path/to/authorized-recording.wav \
  --audio /path/to/another-authorized-recording.wav \
  --output /var/tmp/private-phonemes.json
```

The output filename must be new and outside Git and the model cache.
**The JSON contains private sound transcriptions. Do not upload or commit it.**
Inspect it locally for the agreed test, then delete it. Decoded temporary audio
is removed automatically when the runner exits normally or raises an exception.
After a force-kill, check the chosen temporary directory for leftover files.
Original recordings are never changed or deleted by the runner.

Anyone can repeat the method on their own audio. Private recordings and their
results are not a public, independently reproducible accuracy benchmark.

## Exactly what runs

- Model: [obadx/muaalem-model-v3_2](https://huggingface.co/obadx/muaalem-model-v3_2),
  revision `01a1ef9fbe40d144ef845101e89ff924aed3fef5`.
- Model classes: two files from [official Muaalem code](https://github.com/obadx/quran-muaalem/tree/a0a9e43e71063c8e8367b8cbbb88f6e45d7a65f1),
  revision `a0a9e43e71063c8e8367b8cbbb88f6e45d7a65f1`.
- [Asset pins](muaalem-pins.json) record sizes and SHA-256 hashes. All assets
  are verified before loading; only the two reviewed source modules execute.
  Loading uses local safetensors and rejects missing or unexpected weights.
- CPU float32, eager attention, two compute threads, one inter-op thread and
  seed zero. One model load, no warmup and one run per recording.
- Only the phoneme head is decoded. Standard greedy CTC first combines adjacent
  identical frame predictions, then removes blank ID zero. A blank between two
  equal predictions preserves both. All vowel and QPS sound symbols remain.
- No expected-text prompt, reference alignment, canonical matching or output
  repair. This raw adapter is different from the complete upstream application.

The private report records runtime versions, asset and implementation hashes,
commit/environment information, decoding settings and timings. Inputs are
numbered in argument order. It does not include input paths or audio hashes.
Processing time includes feature extraction, model execution and sound decoding;
audio conversion and model loading are reported separately. This is full-recording
CPU processing, not streaming, browser or phone performance.

The model and its source are MIT licensed. PyTorch is BSD-style and Transformers
is Apache-2.0. The source review covered the two loaded modules; it is not a full
security or training-data audit. Fixed source hashes prevent silent upgrades.
The tradeoff is a large download and custom model code that needs review when
updated. Reusing word-only models would be simpler but cannot directly inspect
sound-level output. No paid inference service or production dependency is added.
Inference stays local; the download step fetches public assets only.

## How to interpret the result

Check whether a deliberately missing sound is absent from the output, and
whether that same sound remains in the intended correct recording. Also check
repetitions. Keep uncertain output uncertain: a model failure is not a mistake
by the reader. Do not treat model agreement as a human-verified transcript.

A few recordings cannot establish a success rate. A larger test needs verified
spoken-sound labels, multiple speakers and both correct and incorrect examples.
The [Muaalem paper](https://arxiv.org/abs/2509.00094) reports several different
metrics; its low error rate on expert recitation does not prove it catches a
learner's omissions. This runner does not calculate a tajweed or recitation score.

Run the offline checks with:

```sh
python -m unittest discover -s benchmarks/recitation/tests -p 'test_*.py' -q
```

CI checks the harness with synthetic inputs. It does not download model weights
or receive private recordings. See also the [next leaderboard candidates](PHONEME-MODELS.md).
