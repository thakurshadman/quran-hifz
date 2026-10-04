# Results from 120 public recordings

**Tilawi had the fewest text differences in all three samples.** All four models
completed all 120 clips: 480 transcriptions, with no processing failures.
This is a promising result for further testing, not proof that Tilawi can reliably
catch a learner’s mistakes.

An exact match means the model output matched the dataset’s expected text after
[comparison normalization](README.md#scoring-and-reference-text). It does not
mean the recitation was correct. For example, a model could fill in a skipped
word and still get an exact match.

## Exact text matches

| Model | OpenSLR (50 clips) | Error dataset (50 clips) | RetaSy (20 clips) |
| --- | ---: | ---: | ---: |
| Tilawi | 47/50 | 29/50 | 6/20 |
| Whisper Tiny | 0/50 | 0/50 | 0/20 |
| Tarteel Base | 41/50 | 22/50 | 1/20 |
| Qur’an Turbo | 40/50 | 22/50 | 2/20 |

## Word differences

A difference is a substituted, missing or added word compared with the supplied
reference. Percentages use total reference words, not an average of clip scores.
They can exceed 100% when the model adds many words. These are **not verified
speech-recognition error rates or learner scores**.

| Dataset | Model | Substituted | Missing | Added | Differences / reference words |
| --- | --- | ---: | ---: | ---: | ---: |
| OpenSLR | Tilawi | 1 | 19 | 0 | 3.01% |
| OpenSLR | Whisper Tiny | 428 | 62 | 208 | 105.12% |
| OpenSLR | Tarteel Base | 12 | 30 | 0 | 6.33% |
| OpenSLR | Qur’an Turbo | 12 | 32 | 0 | 6.63% |
| Error dataset | Tilawi | 14 | 18 | 61 | 37.35% |
| Error dataset | Whisper Tiny | 172 | 36 | 281 | 196.39% |
| Error dataset | Tarteel Base | 26 | 17 | 56 | 39.76% |
| Error dataset | Qur’an Turbo | 24 | 17 | 57 | 39.36% |
| RetaSy | Tilawi | 28 | 8 | 2 | 43.18% |
| RetaSy | Whisper Tiny | 57 | 29 | 196 | 320.45% |
| RetaSy | Tarteel Base | 66 | 1 | 12 | 89.77% |
| RetaSy | Qur’an Turbo | 44 | 6 | 11 | 69.32% |

Reference totals: OpenSLR **664 words**, error dataset **249 words**, RetaSy
**88 words**. Decoded audio totals are about 874.1, 272.0 and 93.7 seconds respectively.
OpenSLR’s lock records source/probed durations (about 878.5 seconds total);
decoded durations are slightly shorter and identical across the four models.

## Source-label groups

These are the publishers’ labels, not independently checked judgments. Empty
error tags do not prove correctness. Counts below are exact text matches.

| Model | Error tags (20) | No error tags (30) | RetaSy “correct” (10) | RetaSy “in_correct” (10) |
| --- | ---: | ---: | ---: | ---: |
| Tilawi | 10/20 | 19/30 | 5/10 | 1/10 |
| Whisper Tiny | 0/20 | 0/30 | 0/10 | 0/10 |
| Tarteel Base | 4/20 | 18/30 | 1/10 | 0/10 |
| Qur’an Turbo | 5/20 | 17/30 | 1/10 | 1/10 |

## Processing times

Median seconds per clip, excluding model loading and audio conversion:

| Model | OpenSLR | Error dataset | RetaSy |
| --- | ---: | ---: | ---: |
| Tilawi | 0.765 | 0.153 | 0.150 |
| Whisper Tiny | 0.955 | 0.690 | 0.709 |
| Tarteel Base | 14.028 | 4.534 | 4.298 |
| Qur’an Turbo | 19.452 | 16.215 | 17.725 |

These timers cover different work: Tilawi measures ONNX inference before text
decoding; Tiny measures its recognition call; the other two include feature
extraction, generation and text decoding. Runs used native CPU, not browser/WASM.
These figures do not establish phone speed or live feedback delay. Each clip ran
once without warmup. Reports include loading time, totals and descriptive p95.

## Important limits

- Samples were fixed before their inference runs. There was no model tuning,
  training or replacement of clips after inspecting model results.
- RetaSy has only 20 clips from 20 distinct source speaker IDs: ten labelled
  correct and ten incorrect. Only two are marked “golden” by the source. This
  is too small to establish performance across learners.
- RetaSy source categories do not verify actual content. One selected reference
  is an opening invocation under a Qur’an category; several use different
  Arabic spellings. These can affect scores. We kept the supplied references
  and scoring unchanged. No qualified content review or spoken-transcript
  verification was performed.
- The error dataset includes only two wording-tagged clips. Letter, vowel and
  tajweed mistakes cannot be assessed by these normalized word comparisons.
- OpenSLR lacks speaker and recitation-convention metadata. Its recordings may
  overlap model training. Qur’an Turbo explicitly names EveryAyah as training
  data; overlap has not been measured. These are not confirmed unseen test sets.
- Whisper output is capped at 128 new tokens, which may truncate some results.
- RetaSy offers research access but has no clear formal dataset license. This
  was temporary local analysis, with no training or redistribution of audio,
  text or personal IDs. Broader reuse rights remain unresolved.

The next useful test needs checked transcripts of what people actually said,
including known skipped or changed words. Matching an expected passage alone
cannot show that the app catches those mistakes. These results do not select
an app architecture or satisfy the M0 acceptance gates.

## Evidence and reproduction

Follow [Public dataset tests](PUBLIC-DATASETS.md) for sources, frozen sample
lists, preparation, inference and cleanup commands. All 120 selected files were
also downloaded again and matched their frozen audio and reference hashes.

The checked reports contain counts, public sample IDs, hashes, model versions
and timings. They contain no audio, reference text, model transcripts or speaker
IDs. Temporary RetaSy audio, text manifests and collected source metadata were
deleted after validation.

| Report | Clean executing commit | Clips × models |
| --- | --- | --- |
| [OpenSLR and error dataset](published/public-100.json) | `438d7b9e0cf4265fd0bb19836f53629245865ae6` | 100 × 4 |
| [RetaSy](published/retasy-20.json) | `0af8b0d35943393b26335d2a3d3644fc60c9424e` | 20 × 4 |

Recorded on 2026-10-04, Linux x86-64, AMD EPYC 9V74 virtual CPU with three
logical CPUs visible; two compute threads and one inter-op thread. Python
3.12.14, Node 24.19.0 and FFmpeg 7.1.5-0+deb13u1. Model assets and dependencies
use the existing pinned versions. The reports record implementation hashes;
the inference and scoring code is identical between these two runs.

All 93 automated benchmark checks passed. They check the harness and failure
handling using test doubles; the 480 real transcriptions above are separate
local evidence, not inference performed by GitHub Actions.
