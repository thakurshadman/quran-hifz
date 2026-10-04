# Qwen3-ASR versus Tilawi

This test compares **Qwen3-ASR 0.6B**, a general multilingual recognizer that
supports Arabic, with our Tilawi baseline. It supports
[ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7).
The app and its production architecture are unchanged.

## Fixed comparison

Use the same [120 frozen public recordings](PUBLIC-DATASETS.md): 50 OpenSLR,
50 error-dataset and 20 RetaSy clips. Each model receives the same decoded mono,
16 kHz float32 samples. The sample lists, text normalization and word-difference
scorer are unchanged. No recordings are replaced or selected based on scores.

Qwen is pinned to `Qwen/Qwen3-ASR-0.6B`, revision
`5eb144179a02acc5e5ba31e748d22b0cf3e303b0`, with checksums for every required
model, tokenizer and configuration file. Its weights occupy 1,876,091,704 bytes
on disk, versus Tilawi’s 88,307,366-byte quantized ONNX model.

Both run locally on CPU, with two compute threads and one inter-op thread.
Load each model once, then process each clip once in fixed order without warmup.
Qwen uses float32, greedy generation, one beam, a 512-new-token limit and Arabic
as the known language. Its context is empty: no expected passage, verse prompt,
canonical matching or forced alignment is supplied.

### Raw output, without repetition cleanup

The official `qwen-asr` 0.0.6 `transcribe()` wrapper rescales audio peaks above 1
and removes extreme repeated characters or short repeated text patterns. Those
steps could change the supplied audio or hide repetitions in the output.

This adapter instead calls the package’s pinned private Transformers inference
helper. It passes the shared PCM directly to the official processor, generation
and token decoder. It keeps decoded repetitions and bypasses the wrapper’s peak
scaling, text repetition cleanup and long-audio chunking. Special control tokens
are removed by the official token decoder; no further transcript repair is done.

This is a **raw-generation comparison**, not the default `transcribe()` workflow.
The helper is a private API, so upgrading `qwen-asr` requires compatibility review
and a new native smoke test. The choice was fixed before inference or score
inspection; no installed package source was modified.

Qwen’s timer covers its processor, generation and token decoding. Tilawi’s timer
covers ONNX inference before CTC text decoding. Both exclude loading, common
audio conversion and downloads. Different runtimes, numeric formats and timer
scopes limit speed comparisons. These timings are not phone performance or the
delay before live feedback. Advertised batched server throughput is a different
measurement.

## Dependencies and reproduction

Qwen uses its official Apache-2.0 package and Apache-2.0 model weights. Its
Transformers/PyTorch CPU backend lets us test the released model without first
building a conversion or a GPU service. PyTorch is BSD-style and Transformers
is Apache-2.0. Tilawi’s model is CC-BY-4.0. Supporting packages include LGPL
`soxr`; no dependency packages or model weights are bundled in this repository.
A future app distribution needs its own license review.

These are isolated research dependencies. The official package also installs
web-demo and alignment dependencies; this test starts no web server and loads
no forced-aligner model. Qwen’s new package and private helper introduce upgrade
risk, addressed here with exact version pins, immutable model hashes, offline
loading, disabled remote model code and native compatibility testing. These
checks are not a complete dependency security or training-data rights audit.

Use Linux x86-64, Python 3.12.14, Node 24.19.0 and FFmpeg. Allow at least 6 GB
free disk space for the environment, assets and temporary files. The host reports about 10 GB RAM, but this workspace has an 8 GiB process
memory limit. Use disk-backed storage, not a RAM-backed temporary directory,
for the environment and model cache. Keep downloads, audio and reports outside Git.

```sh
python3.12 -m venv /var/tmp/qwen-benchmark-env
/var/tmp/qwen-benchmark-env/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.8.0+cpu'
/var/tmp/qwen-benchmark-env/bin/python -m pip install -r benchmarks/recitation/qwen-requirements-linux-cpu.lock
/var/tmp/qwen-benchmark-env/bin/python -m pip check
npm ci --ignore-scripts --prefix experiments/ikhlas-test

/var/tmp/qwen-benchmark-env/bin/python benchmarks/recitation/qwen.py download --cache /var/tmp/qwen-models
/var/tmp/qwen-benchmark-env/bin/python benchmarks/recitation/prepare_datasets.py --destination /var/tmp/qwen-public
/var/tmp/qwen-benchmark-env/bin/python benchmarks/recitation/prepare_retasy.py --destination /var/tmp/qwen-retasy

/var/tmp/qwen-benchmark-env/bin/python benchmarks/recitation/qwen.py run \
  --manifest /var/tmp/qwen-public/openslr132.json \
  --manifest /var/tmp/qwen-public/recitation_errors.json \
  --manifest /var/tmp/qwen-retasy/retasy.json \
  --cache /var/tmp/qwen-models \
  --output /var/tmp/qwen-comparison.json
```

Use new data directories and an output name that does not exist. All model files
and source samples must match their pinned hashes. Preparation downloads assets;
inference then uses local files. No paid service or cloud inference is involved.
After validation, delete the temporary RetaSy directory, including any partial
files after failed preparation. Its formal reuse license remains unresolved.

The Python lock records installed versions, not wheel hashes or a container image.
Reproduction on other hardware may change numerical outputs and timings.

## What this test cannot establish

Expected-text matches are not verified speech error rates or learner scores.
A recognizer could fill in a skipped word and hide the actual mistake. The source
labels, spelling differences, RetaSy opening-invocation reference and unknown
training overlap remain as described in the [public results](PUBLIC-RESULTS.md).

The fixed generation cap can truncate output, particularly repeated output;
completed processing does not prove an untruncated transcript. We do not tune
the cap or repair output after looking at the scores.

Reports publish counts, timing and provenance, not audio, reference text,
transcripts or speaker IDs. No qualified content review, reliable mistake
detection, phone-speed result or M0 acceptance is claimed.
