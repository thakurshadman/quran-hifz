# CROTTC k3: checking the sounds that were spoken

This [ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7) experiment
runs the public [CROTTC k3 model](https://huggingface.co/Haopeng/iqra_CROTTC_conf_k3).
It is related to Utokyo's system, but is not the full leaderboard model.
See [the candidate comparison](PHONEME-MODELS.md).

A useful test has both a deliberately missing sound and an intended-correct
control. The recognizer should keep the omission without inventing one in the
control. Think of checking the sounds someone said before using a spellchecker.
Model output alone does not prove a reader made a mistake.

## Repeat the test locally

Use Linux, Python 3.12.14 and FFmpeg. Keep recordings, model cache and private
output outside Git. Allow several GB for the environment and 1.28 GB for the
released checkpoints. Use disk-backed temporary storage and about 8 GB RAM.

```sh
python3.12 -m venv /var/tmp/crottc-env
/var/tmp/crottc-env/bin/pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.7.1+cpu' 'torchaudio==2.7.1+cpu'
/var/tmp/crottc-env/bin/pip install -r benchmarks/recitation/crottc-requirements-linux-cpu.lock
/var/tmp/crottc-env/bin/pip check
/var/tmp/crottc-env/bin/python benchmarks/recitation/crottc.py download --cache /var/tmp/crottc-model
mkdir -p /var/tmp/crottc-tmp
TMPDIR=/var/tmp/crottc-tmp /var/tmp/crottc-env/bin/python benchmarks/recitation/crottc.py run \
  --cache /var/tmp/crottc-model \
  --audio /path/to/authorized-control.wav \
  --audio /path/to/authorized-mistake.wav \
  --output /var/tmp/private-crottc.json
```

Use a new output name. The JSON contains **private phoneme transcripts**;
inspect it for the agreed test and delete it afterward. Do not publish it.
Temporary decoded audio is removed on normal completion and exceptions; inspect
and clean the temporary directory after a force-kill. Originals remain untouched.
The method is reproducible, but private recordings and their results are not
published. Filenames such as “correct” do not establish verified ground truth.

## Fixed method

[Asset pins](crottc-pins.json) give immutable revisions, sizes and SHA-256 hashes.
Model revision: `0080a8b337e6a78dc12fc3e3fb1b6f0f4c2b1c67`.
WavLM-large configuration revision: `c1423ed94bb01d80a3f5ce5bc39f6026a0f4828c`.
No base WavLM weights are downloaded: the fine-tuned checkpoint supplies them.

- One to ten whole recordings, each at most 60 seconds; mono float32 at 16 kHz.
  FFmpeg downmixes/resamples without trimming or noise removal.
- CPU float32, two compute threads, one inter-op thread, seed zero, one model
  load, no warmup and one pass per clip. Model evaluation disables augmentation.
- WavLM applies waveform layer normalization with epsilon 1e-5, without an
  attention mask or output normalization, matching the upstream single-recording
  path. Its last hidden state feeds two projection blocks and LayerNorm.
- Two-layer Conformer: width 384, eight heads, kernel 3, RoPE attention.
  A 71-way head supplies sound predictions. The auxiliary training head is
  loaded for completeness but is not used for inference.
- Standard greedy CTC combines consecutive equal frame IDs, then removes blank
  zero. Blank-separated repeats remain. No expected verse, language-model repair,
  reference matching or extra repeat removal is supplied.
- The released vocabulary labels only IDs 0–69 despite the 71-way head.
  An emitted ID 70 stays visible as `[UNMAPPED:70]`; it is not guessed or deleted.
  Special tokens remain visible too. These outputs are uncertain hypotheses.

The adapter constructs reviewed modules directly instead of executing the
released training YAML. Checkpoints use `torch.load(weights_only=True)` and
strict key/shape matching. Inference is local with Hugging Face offline mode.
Reports contain input indices rather than filenames or audio hashes, plus
runtime versions, environment/commit information, implementation hash and pins.
Timing includes normalization, model execution and decoding; loading and audio
conversion are separate. It is not phone, browser or streaming latency.

## Dependencies and limits

The isolated [runtime lock](crottc-requirements-linux-cpu.lock) records installed
versions, not wheel hashes. SpeechBrain 1.0.3 and Transformers 4.57.6 use Apache-2.0;
PyTorch/Torchaudio 2.7.1 CPU use BSD-style licenses. Model weights are Apache-2.0.
The model configuration and [upstream inference code](https://github.com/Secondtonumb/IF-MDD/tree/cca150ec4ff00e01d61a613092d1d178e661dfb2)
were inspected to reproduce its architecture. This is not a complete dependency or training-data audit.
Updates require reviewing the pins and rerunning strict-load and regression checks.

Using SpeechBrain avoids a custom rewrite of its Conformer. It adds environment
size and dependency maintenance; no paid service or app dependency is introduced.
An ONNX/browser conversion would be a separate experiment. Existing word-only
recognizers remain useful baselines but do not expose these sound predictions.

This harness does not calculate an accuracy, pronunciation or tajweed score.
A few personal recordings cannot establish a detection rate. A larger comparison
needs human-checked spoken labels, multiple speakers and controlled false-alarm
measurement. Published IqraEval scores are not results from this private test.

```sh
python -m unittest discover -s benchmarks/recitation/tests -p 'test_*.py' -q
```

CI checks the harness with synthetic inputs, not downloaded models or private audio.
