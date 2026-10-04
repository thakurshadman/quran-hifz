# ASR feasibility plan and initial backlog

**Status:** Proposed. No model selected, dataset collected, or benchmark run.
**Milestone:** M0 — prove real-time word-level recitation tracking at acceptable
accuracy, latency, privacy, and cost before product architecture is fixed.

Read the [PRD](../product/PRD.md), [NFR-001](../requirements/NFR-001.md),
[test strategy](../testing/TEST-STRATEGY.md), and [security rules](../../SECURITY.md).
ASR means automatic speech recognition; it is not tajwīd assessment.

## Experiment design

1. Approve scope, recitation convention, licensing, consent/storage, speaker
   recruitment, reference devices, metrics, cost ceiling, and false-error limits.
2. Build a consented/licensed corpus with ground-truth word events, error labels,
   and timing annotations. Begin with a controlled subset of Juz 29. Include
   correct recitation, deliberate omissions/substitutions, repeats, corrections,
   pauses/stops, similar passages, and āyah transitions. Include realistic
   microphones/noise and diverse recitation speeds/voices; do not treat a single
   professional reciter as representative of learners.
3. Split train/tune/test by speaker and source recording to prevent leakage;
   isolate passages where practical and report unavoidable overlaps. Freeze test
   manifests and scoring rules before candidate comparison. Annotators work
   independently, with disagreements adjudicated by qualified content reviewers.
4. Evaluate candidate recognizers under matched inputs and declared settings:
   general Arabic, Qur’an-adapted, local/browser/native-capable, remote, and hybrid
   approaches where licensing/resources permit. This is a comparison plan, not
   authorization to purchase services or transmit participant data.
5. Compare unconstrained and Qur’an-constrained decoding. A constrained model
   may hallucinate the expected words across an actual omission; assess error
   recall/false acceptance as well as normal-recitation word accuracy.
6. Exercise real streaming: partial revisions, chunk boundaries, delayed/duplicate
   updates, pauses, reconnects, backtracking, and cancellation. Measure warm/cold
   paths, stability delay, resource use, and end-to-end latency rather than only
   batch transcription speed.
7. Publish reproducible aggregate results, limitations, costs, privacy/rights
   review, and a go / conditional / no-go recommendation in a proposed ADR.

Do not put private audio/transcripts in this public repo. A public result should
contain sanitized aggregate metrics and non-identifying manifest references;
participant consent does not automatically authorize public redistribution.

## Measurement protocol and decision gate

ASR-001 proposes corpus size/cohort quotas and holdout rules before collection;
ASR-002 supplies event matching, treatment of uncertainty, annotation quality,
sample-size rationale, confidence intervals, and predeclared A03 thresholds.
Report word error rate as a diagnostic, not a proxy for correct ḥifẓ feedback.
Uncertain events must remain in denominators where specified by NFR-001.

Store reproducible commands/configuration, model/data versions and hashes,
hardware/browser details, timestamps, seeds, and sanitized results with each
experiment. Measure end-to-end feedback against manually annotated acoustic word
ends; measure stable final feedback separately. Performance on test recordings
cannot establish unsupported tajwīd capability or generalize to untested cohorts.

**Go:** all approved accuracy/error, latency, privacy, rights, and cost gates pass
on the held-out cohort/device matrix with sufficient evidence. **Conditional:**
limitations or unresolved thresholds remain and need bounded additional work.
**No-go:** evidence fails a gate or viable rights/privacy conditions cannot be met.
The human owner accepts the decision; agents must not silently relax thresholds.

## Backlog

These IDs are canonical; associated GitHub issues carry the same ID in the title.
All are planned unless their issue/PR records completion. Creating a ticket is
not approval of unresolved numerical targets, providers, data collection, or spend.

| ID | Deliverable and acceptance criteria | Depends on |
| --- | --- | --- |
| PROD-001 | Phase 0 governance: all agreed documents present, requirements traceable, open decisions explicit, independent review/QA evidence and human PR review | None |
| QA-001 | CI/bootstrap gates: select/pin documentation tools, validate links and document structure on PRs; demonstrate a seeded failure is caught; propose repository required checks/approvals with human configuration evidence | PROD-001 |
| SEC-001 | Privacy/threat model and reporting: approve consent/access/retention/withdrawal controls, designate security and content reviewers, establish private vulnerability reporting before release | PROD-001 |
| ASR-001 | Benchmark dataset specification: sources/rights, convention, labelled cases, cohort/sample-size plan, independent annotation/adjudication, speaker/source-disjoint holdout manifest; no collection before consent approval | PROD-001, SEC-001 |
| ASR-002 | Accuracy protocol: define all event denominators/matching rules, WER, recall, precision, false accusations/acceptances, uncertain coverage and confidence intervals; ratify A03 limits before evaluation | ASR-001 |
| ASR-003 | Latency/resource protocol: instrumentation from acoustic event to UI, stage breakdown, warm/cold paths, reference device/network matrix, soak/resource budgets and reproducible harness | PROD-001 |
| ASR-004 | Candidate evaluation: compare viable recognizers on frozen corpus under shared protocol; record licenses, versions, settings, cohort metrics, exclusions and reproducible commands | ASR-001, ASR-002, ASR-003 |
| ASR-005 | Streaming behavior: test partial revisions, chunk sizes, stability, repeats, correction, reconnect/cancel and failure modes; report latency and state regressions | ASR-004 |
| ASR-006 | Qur’an-constrained decoding: controlled ablation versus unconstrained baseline; test omissions/substitutions and similar passages; quantify false acceptance and integrity risks | ASR-004 |
| ASR-007 | Browser/on-device feasibility: compare supported candidate paths on named devices/browsers; record memory, battery/resource proxy, model size, startup/download, offline capability and gaps | ASR-004 |
| ASR-008 | Cost model: establish human-approved ceiling; compare measured cost/session and declared 100/1,000-user scenarios, local/remote tradeoffs, assumptions and sensitivity | ASR-004 |
| ASR-009 | Candidate privacy analysis: document actual audio flows, provider retention/training/region/terms and deletion, local exposure, consent UX, and unresolved constraints | SEC-001, ASR-004 |
| ASR-010 | Recommendation/ADR: consolidate accuracy, error, latency, compatibility, integrity, cost and privacy evidence; state go/conditional/no-go and obtain human decision | ASR-005, ASR-006, ASR-007, ASR-008, ASR-009 |
| ARCH-001 | Architecture bake-offs: after M0, compare frontend options on the same slice and measure whether Rust/WASM adds value; propose boundaries/ADRs without assuming a framework | ASR-010 human go decision |

QA-001's executable checks and the relevant research/consent specifications must
be ready before dependent experiment code is merged or recordings collected.
No feature tickets are implementation-ready until requirements and architecture
are accepted. Technical spikes use isolated research branches and are not quietly
promoted into production.
