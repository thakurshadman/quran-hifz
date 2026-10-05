# Does Tilawi keep repeated audio?

This small test checks one part of [ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7):
what happens when we play exactly the same audio twice? It does not change the app.

Think of a recording saying “A B C.” We play it twice, with a short pause.
If Tilawi first writes “A B C,” we check whether the double recording gives
“A B C A B C.” This tests consistency. It does not prove that “A B C” was a
correct transcript in the first place.

## Result

**Tilawi did not pass this strict repetition check.** None of the nine pairs
with a nonempty original transcript produced exactly two copies of that
transcript. One original produced no words, so that pair could not be compared.

| Outcome | Pairs |
| --- | ---: |
| Exact two-copy output | 0 |
| Exact one-copy output | 0 |
| Other output | 9 |
| Cannot compare: empty original output | 1 |
| Total | 10 |

All 20 inputs completed without a processing failure. An empty transcript is
still a recorded outcome. The nine changed outputs do **not** prove that Tilawi
removed every repetition or silently corrected the recitation. They show that
we cannot assume doubled audio will produce doubled text.

As a separate check, 8 of 10 original outputs matched the supplied passage;
none of the double outputs matched the doubled passage. The original word
counts matched our earlier Tilawi run on all ten clips. Median CPU inference
took **0.485 seconds** for originals and **0.971 seconds** for doubles.

The [full report](published/repetition-20.json) records all ten pairs, counts,
timings and source/model/software hashes. It was run from clean commit
`8d673c55d930f6be92734993802e364b83965a08`, before results were added. The machine
was Linux x86-64 on an AMD EPYC 9V74 virtual CPU, with three logical CPUs visible.
All 133 benchmark tests and 30 documentation tests passed. These code tests are
separate from the 20 real model inputs.

Next, inspect repeated speech with verified word transcripts before relying on
Tilawi for hifz feedback. This test alone cannot identify the cause or choose a
replacement model.

## Fixed test

- Use the first ten eligible clips in our frozen OpenSLR sample list. A clip
  must decode to at most 14.75 seconds. We skipped 24 longer clips before reaching
  ten. We did not select clips based on model scores.
- Decode each clip once to mono, 16 kHz float32 audio. Make its double by copying
  those exact bytes, adding 0.25 seconds of silence, then copying the bytes again.
  No words are synthesized, removed or rearranged. Both copies stay identical.
- Freeze source, reference and decoded-audio hashes before running the model.
  The [sample list](repetition-samples.json) records them without audio or text.
- Run the existing Tilawi model and decoder unchanged. Use one model load,
  two compute threads, no warmups and one pass per input. Run each original
  immediately before its double: **20 inputs from 10 source clips**.
- Keep the existing text normalization. It removes punctuation and vowel marks;
  it does not test pronunciation or tajweed. No expected passage goes to Tilawi.

Each pair gets exactly one result:

| Result | Meaning |
| --- | --- |
| Exact two-copy output | The double’s words equal two copies of the original’s words. |
| Exact one-copy output | The double’s words equal just one copy of the original’s words. |
| Other output | The words differ in another way. We cannot call this a lost repeat. |
| Cannot compare | The original produced no words. This remains in the total. |

Even a one-copy output would not prove the model deliberately corrected a
recitation. A longer input can change recognition for other reasons. Separately,
we compare each output with the source’s supplied passage, doubled where needed.
Those passages have not been independently checked against the speech.

## Repeat the test

Use Python 3.12.14, Node 24.19.0 and FFmpeg on Linux. No new Python packages or
model downloads beyond the existing Tilawi setup are needed. Node packages stay
pinned in the existing lockfile. Model inference stays local and uses no paid API.
The source publisher declares MIT; Tilawi declares CC-BY-4.0. See the
[source notes](PUBLIC-DATASETS.md) and [model details](README.md).

From the repository root:

```sh
npm ci --ignore-scripts --prefix experiments/ikhlas-test
python benchmarks/recitation/benchmark.py download --cache /var/tmp/tilawi-models --models tilawi
python benchmarks/recitation/prepare_datasets.py --destination /var/tmp/tilawi-public
python benchmarks/recitation/repetition.py \
  --manifest /var/tmp/tilawi-public/openslr132.json \
  --cache /var/tmp/tilawi-models \
  --output /var/tmp/tilawi-repetition.json
python -m unittest discover -s benchmarks/recitation/tests -p 'test_*.py' -q
```

Use a new destination and report name. The shared preparation command also fetches
our earlier error-dataset subset; this test uses only OpenSLR. Keep all downloads
outside Git. Changed source or decoded-audio hashes stop the run, rather than
silently changing the test. FFmpeg versions can change decoded bytes; use the
version recorded in the report. A failed run produces no partial score report.

Temporary decoded and doubled audio is removed when the test finishes or fails.
Transcripts stay in local process memory and pipes, not reports. Reports contain
hashes, counts, timings and software versions. We do not publish audio or text.
CPU timing excludes loading and audio conversion; the Tilawi timer also excludes
text decoding. It does not measure phone speed or live feedback delay.

## What still needs testing

**Missing words and wrong words remain untested by this experiment.** We need
recordings with verified transcripts of what the person actually said. For
example, if the audio says “A B D,” the reference must also say “A B D,” even
when the intended passage says “A B C D.” Otherwise a model that invents “C”
could wrongly receive a perfect score.

We checked the suggested public sources on 2026-10-05:

| Source | What we can use or still need |
| --- | --- |
| [QuranMB.v2](https://huggingface.co/datasets/IqraEval/QuranMB.v2) | 1,642 clips. The [public references](https://huggingface.co/datasets/IqraEval/test_references) use speech sounds, not ordinary word transcripts. [Error labels](https://huggingface.co/datasets/IqraEval/IqraEval_Test_GT) require access. This needs a separate pronunciation test; audio reuse terms also need checking. |
| [Recitation Errors Test](https://huggingface.co/datasets/sobolev210/quran-recitation-errors-test) | Its metadata is byte-for-byte identical to the source we already used. Only two Hafs clips carry a wording tag; both were already in our sample. Tags do not supply the wrong words actually spoken. |
| [Quranic ASR Benchmark](https://huggingface.co/datasets/Quran-Lab/quranic-asr-benchmark) | Its public card describes ten corrected repeat references, including 51:56 → 51:57 → 51:56. Audio requires manual access approval. We did not run those clips. |

The checked revisions are `75afc3391e47ca005af286b2518d8a2edf98da5d`
(QuranMB.v2), `a5efade58cdb5df3a40f9619907279bc76a8ee32` (Errors Test),
and `d9fc635276a6a2b770293e6bffbe5b077bfc52b0` (Quranic ASR Benchmark).
No gated terms were accepted and no gated audio was downloaded.

Copied studio recordings are easier than a person repeating words naturally.
These ten clips were used in earlier comparisons, and model training overlap is
unknown. This is not a held-out learner test, a mistake-detection score, a qualified
Qur’an-content review or proof that the app is ready.
