# Public dataset tests

The first test used one recording. This follow-up compares the same four models
on **120 public clips: 50 OpenSLR clips, 50 error-dataset clips and 20 RetaSy clips**.
It is a small exploratory
comparison. It does not establish learner mistake detection or phone performance.

## Sources investigated

| Dataset | Finding | Decision |
| --- | --- | --- |
| [RetaSy](https://huggingface.co/datasets/RetaSy/quranic_audio_dataset/tree/b1fcc39cbc045f367bb07e39025a0e3aaeabf34f) | 6,828 clips; authors report 1,287 participants and 1,166 labelled clips. Labels describe broad correctness, not actual spoken words. | Selected 20 clips for temporary local analysis using the authors' offered research access. No formal dataset license found; rights remain unresolved for broader use. |
| [OpenSLR 132](https://www.openslr.org/132/) through [deepdml](https://huggingface.co/datasets/deepdml/Quran_Speech_Dataset/tree/9e3ddb53c201369c997ae1f8e2e0232a0e275cd0) | Original publisher declares MIT. Mirror has 123,971 clips with audio, duration and expected text. | Selected 50 clips. The mirror does not provide speaker IDs or error labels. |
| [Quran recitation errors](https://huggingface.co/datasets/sobolev210/quran-recitation-errors/tree/d196cd3132c69cd361d28cf6a8b442ae4e0bf0b4) | Publisher declares MIT. 1,042 clips; metadata contains 451 Hafs and 591 Qaloon clips. Annotation method and original collection details are undocumented. | Selected 50 Hafs clips for a descriptive comparison under the published terms. Error tags are unverified. |
| [Qur’anic Universal Ayahs](https://huggingface.co/datasets/QUD-Technologies/quranic-universal-ayahs/tree/8ca67b4213b761cb364c17923548295ef2d58301) | Many reciters and word timings. Its card explicitly says the audio is not relicensed. | Deferred: check original recording rights. |
| [Quran-MD](https://huggingface.co/datasets/Buraaq/quran-md-ayahs/tree/669e9c4b78716d4558cebab98e1072564801fbb0) | 187,080 verse clips and 30 reciters. | Deferred: no explicit license found in the dataset cards. Professional recordings may overlap other sources. |

RetaSy sources checked include its [paper](https://arxiv.org/html/2405.02675v1),
[website](https://quranic-audio-dataset.github.io/) and
[website source](https://github.com/Quranic-Audio-Dataset/Quranic-Audio-Dataset.github.io/tree/05b34904aa0dd18f3924be56b64c69169335fe49).
The paper's own license does not license its audio. The dataset card explicitly
offers download instructions and describes AI research use. This user-requested
local analysis relies on that offered access, not on an invented license grant.
It does not train a model or redistribute the recordings, text or personal IDs.
The RetaSy downloads and local text manifests are temporary and deleted after
validation. Formal rights for training, redistribution or product use remain
unresolved. We have not contacted the authors.

OpenSLR and the error dataset are evaluated locally under their published MIT
declarations. This is not an audit of every original recording's ownership or
participant consent. Audio, reference text and personal metadata are not
redistributed here. None of these sources has received our qualified content review.

## How the samples were chosen

Each list was fixed **before inference on that sample**. [public-datasets.json](public-datasets.json)
records source revisions, row numbers, reference/audio hashes, selection rules,
exclusions and clip durations for the first 100 clips. The supplementary RetaSy
list is in [retasy-samples.json](retasy-samples.json). Seed: `20261004`.

- OpenSLR: shuffle candidate row indices across all 123,971 rows, then take the
  first 50 eligible clips. The source has no speaker field, so voice diversity
  cannot be confirmed from this mirror. It also lacks recitation-convention
  metadata; legitimate differences between conventions may affect text scores.
- Recitation errors: Hafs only. Shuffle clips with error tags and clips without
  tags separately. Select up to 20 tagged clips, then fill to 50 with untagged
  clips, with at most three clips per source recording. A recording is not
  necessarily a unique speaker. Empty tags do not prove correct recitation.
- RetaSy: select 10 clips labelled `correct` and 10 labelled `in_correct`, Hafs
  only, with no repeated source speaker ID. Use a seeded subset of metadata
  pages and seeded shuffling before selection. Accept only the clear Qur’an
  passage labels listed in the lock; exclude adhān and other prayer categories.
  These are dataset labels, not
  our independently verified judgments or word-by-word spoken transcripts.
- All three: recordings must be 1–30 seconds and have 1–500 normalized reference
  words. Remove exact duplicate downloaded audio across the samples. Longer
  clips are excluded, not cut. This biases the comparison toward short clips.

The selected error-dataset clips cover 29 source recordings: 20 clips have tags
and 30 do not. Of the 20 tagged clips, 15 have `Letters`, five `Tajweed`, two
`Wording`, and one `Tashkeel` tags; categories overlap. Only two clips carry a
wording tag, so this sample cannot establish reliable word-mistake detection.

We did not tune or train models using these clips. Upstream training overlap is
unknown, and exact-byte checks cannot detect the same recording in another
encoding. These are not confirmed unseen test sets. They also do not establish
coverage of the proposed Juz 29 learner benchmark in #4/#7.

In particular, [Qur’an Turbo's pinned model card](https://huggingface.co/naazimsnh02/whisper-large-v3-turbo-ar-quran/blob/670f826cf3731ae9f6b3f54d4a417d8f600e2cd2/README.md)
names EveryAyah as its training dataset. Shared professional recordings are a
real overlap concern; we have not matched this sample against its training files.

## Repeat the test

First follow the [installation and model-download guide](README.md).
The preparation command uses Python's standard library; no extra dependencies
are needed. Keep data and reports outside every Git checkout.

```sh
/tmp/quran-benchmark-venv/bin/python benchmarks/recitation/prepare_datasets.py \
  --destination /tmp/quran-public-samples

/tmp/quran-benchmark-venv/bin/python benchmarks/recitation/batch.py \
  --manifest /tmp/quran-public-samples/openslr132.json \
  --manifest /tmp/quran-public-samples/recitation_errors.json \
  --cache /tmp/quran-models \
  --models tilawi tiny tarteel quran-turbo \
  --output /tmp/quran-public-results.json

/tmp/quran-benchmark-venv/bin/python benchmarks/recitation/prepare_retasy.py \
  --destination /tmp/quran-retasy-samples

/tmp/quran-benchmark-venv/bin/python benchmarks/recitation/batch.py \
  --manifest /tmp/quran-retasy-samples/retasy.json \
  --cache /tmp/quran-models \
  --models tilawi tiny tarteel quran-turbo \
  --output /tmp/quran-retasy-results.json
```

The published evidence uses two separate runs: the first two datasets together,
then RetaSy separately. Keep that order and process separation when comparing
timings. After validating the RetaSy result, delete its temporary sample directory
to remove the downloaded audio and text manifests.

Use a new destination and output name for each run. Preparing downloads only
the selected audio and small metadata files, not the full datasets. OpenSLR
uses Hugging Face's viewer audio, which may be converted from the original.
The viewer must report the pinned revision; every reference and downloaded
audio file must match its frozen hash. If the viewer changes or removes files,
preparation fails rather than silently replacing examples. No perpetual hosting
availability is promised.

An interrupted preparation can leave downloaded files in its destination.
Delete that directory or choose a new one before retrying.
For RetaSy, also delete the partial temporary directory after failed preparation.

Inference is offline after preparation. Each clip is decoded once to mono,
16 kHz float32 audio; all models receive that same decoded clip. Models load
once, with two compute threads, zero warmups and one pass through the list.
Model versions and decoding match the original comparison. No model receives
the expected text as a prompt.

Whisper generation is capped at 128 new tokens, as in the first comparison.
That can truncate a long transcription even when its audio fits within 30 seconds.
Such differences remain in the totals; a completed run does not prove that every
transcript was complete.

## What the numbers mean

The reference is the dataset's expected passage, unchanged. We apply the same
[comparison normalization](README.md#scoring-and-reference-text) to reference
and model output. We do not remove basmala or repair either text after seeing
model output. The source text is never rewritten or presented as verified
display text for the app.

For each dataset and tag group we report:

- **Word differences:** total substituted, missing and added words divided by
  total reference words. This is word-weighted, not the mean of clip percentages.
- **Exact matches:** clips with zero word differences divided by tested clips.
- **Processing time:** median, descriptive p95 and total time. Model loading
  and audio conversion are separate. The first clip includes first-use effects.

These references are not independently checked transcripts of actual speech.
So these numbers are **not verified ASR word error rates or recitation scores**.
Example: if someone skips a word but the model fills it in, matching the expected
passage can hide that mistake. Letter, vowel and tajweed tags also cannot be
tested by a scorer that removes vowel marks. Tagged groups are descriptive only;
we do not derive error-detection recall, precision or false-warning rates.

Timer scopes still differ: Tilawi times ONNX inference before its text-decoding
loop; Tiny times the whole recognition call; Python Whisper includes feature
extraction, generation and text decoding. Native CPU timings cannot establish
browser speed or time to live feedback. Fifty clips per source do not justify
reliable tail-latency or population accuracy claims.

Reports contain counts, times, hashes and public sample IDs, with no reference
text, model transcripts or speaker IDs. Temporary decoded audio is removed
after each run. Downloaded source audio and local manifests remain until the
operator deletes their chosen directory. A processing failure aborts the run;
it does not count as a recitation error or produce a misleading partial report.

## Validation and next step

The automated checks exercise preparation, integrity, aggregate scoring and
failure behavior. They do not download these datasets or run the real models
in GitHub Actions. Real-model evidence is recorded with the results and PR.

Next, establish checked spoken transcripts and reliable word-error labels on
separate speakers before claiming the app catches memorization mistakes.
This comparison supports ASR-004 (#7); it does not close #4, #5 or M0.
