# Original exploratory result: one Al-Ikhlas recording

These are the results originally reported in the conversation, preserved for
transparency. They were produced by temporary scripts that this directory now
packages into a reusable harness; they are **not** a fresh execution of a public
benchmark corpus. The private audio and raw transcriptions are not published.

## Observations

Input: one 16.8-second, 48 kHz stereo PCM16 recording, converted by FFmpeg to
mono 16 kHz float32. Reference scope: the 15 words of Al-Ikhlas without basmala.
One measured inference per model, no warmup, two configured compute threads.

| Model | Substitutions | Deletions | Insertions | Total word differences | Inference time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tilawi mixed-quantized FastConformer | 0 | 0 | 0 | 0 | 1.13 s |
| Qur’an Whisper Large-v3-Turbo | 2 | 0 | 0 | 2 | 19.95 s |
| Tarteel Whisper Base Arabic Qur’an | 3 | 0 | 0 | 3 | 11.86 s |
| Generic Whisper Tiny q8 | 7 | 2 | 0 | 9 | 1.07 s |

Exact model revisions and assets are in [models.json](models.json). Runtime:
Python 3.12.14, Transformers 4.57.6, PyTorch 2.8.0 CPU; Node 24.19.0,
Transformers.js 4.3.0 and ONNX Runtime Node 1.30.0. FFmpeg was
7.1.5-0+deb13u1 on Linux x86-64 with an AMD EPYC 9V74 virtual CPU.
PyTorch served the two larger Whisper models; ONNX served Tilawi and Tiny.
Times exclude model loading/download and file decoding, and are not phone or
streaming latencies. Tilawi measures ONNX `session.run`, excluding greedy CTC
text decoding; Tiny measures its pipeline call; Python Whisper includes feature
extraction, generation and text decoding. These timer-scope, quantization and
runtime differences limit direct speed comparisons.

## Corrections and interpretation

The initial scoring draft accidentally included a reference-file basmala prefix
and described those four missing words as the opening verse. That statement was
corrected: the models did recognize the opening verse. The final scoring scope
explicitly excludes the prefix and has 15 words. Superscript waw/yeh must also be
removed by the documented comparison normalization; Unicode combining-mark
removal alone misses them. The regression suite guards these two mistakes.

An independent checker recomputed reference scope and minimum edit distances
for all four outputs. No human-verified transcript of the actual speech was
created, so these are differences from the intended canonical passage, not
proof that the user made a mistake or a general model WER claim.

Tilawi was the most promising candidate **for this recording**. Matching the
expected words does not prove sensitivity to deliberate errors, pronunciation,
tajwīd, other speakers/noise, or browser/phone performance. The next experiment
must include known omissions and substitutions rather than only fluent correct
recitation. `Muno459/fastconformer-quran` was unavailable without manual access
approval and was not included.

## Reproducing and extending

The packaged harness was exercised against the same private recording during
implementation. All four edit counts matched the original: Tilawi 0, Tiny 9,
Tarteel 3 and Qur’an Turbo 2. Fresh single-run times were approximately 0.88 s,
1.09 s, 12.21 s and 19.30 s respectively; this illustrates that timing varies.
That check validates the packaging, not a new independent recording or dataset.
The report remains local because it contains the private input's fingerprint.

Follow the [README](README.md) to run the same preparation, model pins and scoring
rules. The exact original numbers cannot be independently reproduced without
the original private audio. Using other audio reproduces the method, not that
observation. Timing also depends on hardware and system load.

Future comparable reports should retain local input hashes, configuration,
reference scope, model asset hashes, runtime/device versions and all measured
runs. Public accuracy claims require appropriately licensed/distributable data,
human-checked actual-speech transcripts and a representative evaluation design.
Do not publish private recordings or transcripts merely to make a result public.
