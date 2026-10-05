# Three candidates after whu-iasp

These are the next three teams on the
[frozen IqraEval leaderboard snapshot](https://huggingface.co/datasets/IqraEval/leaderboard_data/blob/6f3a28e6e2e8ba3767cbb2b94a4928d46acc238d/leaderboard.tsv).
Research checked on 2026-10-05 (UTC), for
[ASR-004 #7](https://github.com/thakurshadman/quran-hifz/issues/7).

**Utokyo is the most practical next lead:** public code and related model weights
exist. That does not yet make its full leaderboard result reproducible.

| Rank | Team | Error-detection F1 | Approach | Can we test it? |
| --- | --- | --- | --- | --- |
| 2 | RAM | 71.94% | Wav2Vec2 trained with carefully cleaned labels and filtered audio | No verified public model or code release found |
| 3 | Utokyo | 71.70% | CROTTC-IF predicts sounds without an expected sentence during inference | Related models are public; the full Arabic IF model requires access approval |
| 4 | SQZ_ww | 69.96% | U2++ Conformer trained with synthetic mistakes and two-pass decoding | No verified public model or code release found |

F1 balances catching mistakes with avoiding false alarms; higher is better.
It is not the percentage of all recitations judged correctly. These are published
phoneme-mistake scores, not results from our recordings or complete tajweed tests.
The three phoneme error rates are 4.02%, 3.72% and 4.02%, respectively; lower
means fewer sound-transcription errors on that benchmark.

The [challenge overview, section 4](https://www.isca-archive.org/interspeech_2026/kheir26b_interspeech.pdf)
describes their methods. Its earlier snapshot puts RAM third at 71.57% F1;
the table above uses the later leaderboard. Not finding a release does not
prove that none exists. RAM and SQZ_ww licenses remain unverified.

## What is available for Utokyo

The [team's paper](https://www.isca-archive.org/interspeech_2026/geng26_interspeech.html)
links its [Apache-2.0 code](https://github.com/Secondtonumb/IF-MDD/tree/cca150ec4ff00e01d61a613092d1d178e661dfb2).
It reports 71.70% F1 with CROTTC-IF and acoustic decoding weight 0.9.

| Model | Access / license | Published F1 | Frozen revision |
| --- | --- | --- | --- |
| [CROTTC k3](https://huggingface.co/Haopeng/iqra_CROTTC_conf_k3) | Public, Apache-2.0 | 69.71% | `0080a8b337e6a78dc12fc3e3fb1b6f0f4c2b1c67` |
| [CROTTC k7](https://huggingface.co/Haopeng/iqra_CROTTC_conf_k7) | Public, Apache-2.0 | 68.75% | `c260522657737b09480deb2acd4a3688353f1efc` |
| [Arabic IF model](https://huggingface.co/Haopeng/iqra_IFMDD_Con) | Manually gated; license unverified | Exact released-checkpoint correspondence unverified | `e48854bd7023ce5152c8ec7f4ac021756ea38d3d` |

The public k3/k7 figures are single-checkpoint, greedy-decoding results from
their model cards. They are **not the full 71.70% system**. Their configurations
include custom modules and original-machine paths, so a reviewed adapter is
needed before local use. No weights from these three teams were run in this
research step. Start with k3 if a follow-up test is approved; use the same known
omission and intended-correct control, then expand to verified public examples.

The separate [Muaalem experiment](MUAALEM.md) provides the current raw-sound test
method. Its numbers must not be compared directly with IqraEval scores from a
different dataset and evaluation method.
