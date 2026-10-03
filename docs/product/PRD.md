# PRD v0.1 — Qur’an Ḥifẓ Testing

**Status:** Draft for human review, 2026-10-03.
**Source:** [Planning conversation](https://chatgpt.com/share/6ac1905c-d320-83ea-af8f-a2816b4cf3b0).
**Owner:** Human repository owner; approval is not implied by this draft.

## Problem and outcome

People memorizing Qur’an need an affordable, focused way to test continuation
from random passages in material they know. The core interaction is: choose a
scope → hear an authentic recorded prompt → continue aloud → receive immediate,
honest word-level feedback → start the next question.

Priorities are Qur’anic integrity, trustworthy feedback, sub-second responsiveness,
privacy, low operating cost, and a fast repeatable test flow. Software feedback
supports memorization practice; it does not establish tajwīd correctness.

## Milestones

- **Phase 0:** establish requirements, governance, research plan, and backlog.
  This PR contains documentation only.
- **M0 — Technical Feasibility:** determine whether real-time recitation tracking
  is viable at acceptable accuracy, latency, privacy, and cost. Research uses
  controlled, licensed/consented material and explicit experiment tickets.
- **MVP:** after M0 and accepted ADRs, deliver random prompted testing in the
  initial scope. M0 is not a commitment to ship an unvalidated recognizer.

## Functional requirements and acceptance criteria

IDs remain stable as the draft evolves. Tests are planned in
[TEST-STRATEGY.md](../testing/TEST-STRATEGY.md); none exist yet.

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| FR-001 | Select known material | Select one or multiple sūrahs within initial Juz 29 scope, or all Juz 29; reject empty/unsupported selections; every generated prompt and scored continuation stays in the selected scope. Expansion to other ajzāʾ is later. |
| FR-002 | Random authentic prompt | Choose a valid location using testable random selection; play a licensed recording by an approved qāriʾ with verified text/timing linkage. No synthesized prompt audio. Same seed/configuration reproduces selection in tests. |
| FR-003 | Capture a continuation | Start only after user action and permission; show capture state; allow stop; handle denied/lost microphone without scoring failure; release capture on completion/cancel. |
| FR-004 | Stream recognition | Process incremental, revisable hypotheses while recitation continues; handle late, duplicate, and out-of-order updates without corrupting state. Document adapter timing/confidence semantics. |
| FR-005 | Evaluate word sequence | Distinguish correct, omitted, substituted, repeated, self-corrected words, premature stops, and continuation into the next āyah. Deterministic alignment fixtures cover each case and selected-scope boundaries. |
| FR-006 | Show honest live feedback | Separate tentative/uncertain states from confirmed outcomes; uncertainty/provider failure is not a definite mistake. Preserve display text, allow correction of provisional feedback, and provide accessible non-color cues. |
| FR-007 | Permit self-correction | A specified correction window accepts supported backtracking/correction without double-counting or permanently penalizing a repaired tentative mismatch. Window and finalization rules require a specification before implementation. |
| FR-008 | Finish and repeat | Explicitly finish/cancel a question, show confirmed versus unresolved results, and start a new question with clean state. Scoring formula and end-of-answer rules remain TBD; never fabricate a score from uncertain speech. |
| FR-009 | Deterministic difficulty | Define Very Easy, Easy, Medium, and Hard independently of recognition, with valid prompt/continuation bounds. Very Easy uses a recognizable āyah opening and a longer cue; Easy gives sufficient context; Medium may begin deeper in a passage; Hard uses a short cue and less context. Exact cue lengths and valid timing granularity require specification and licensed metadata. |
| FR-010 | Preserve data provenance | Version and checksum authoritative display text, derived comparison data, stable identifiers, and prompt recordings. Normalization never changes display text; reject unverified/mismatched assets. |

The benchmark starts with a controlled subset before expanding to Juz 29.
Passage/word boundary conventions and recitation tradition must be fixed in the
dataset specification, not assumed. Reference prompts must finish or otherwise
be isolated from microphone evaluation to prevent prompt audio being scored as
the user's answer; the interaction design must specify this before implementation.

## Quality and success targets

See [NFR-001](../requirements/NFR-001.md) for metric definitions and evidence.
Initial research targets from planning: ≥98% correct-word acceptance; ≥95%
omission and substitution detection; alignment p95 ≤5 ms; M0 end-to-end partial
feedback p95 ≤1 second, with an MVP target ≤800 ms. These are hypotheses to
validate, not current capabilities. False accusations, false acceptance, and
uncertainty coverage must also be measured to avoid misleading aggregate scores.

## Data and privacy

Use verified authoritative text and authentic qāriʾ recordings with proven rights.
Never generate Qur’anic text/audio. Keep display and comparison representations
separate. Record reciter, convention, source, license, version, checksum, sūrah,
āyah, and timing metadata. Elevated review applies to text/data changes.

Prefer minimal audio exposure. Local inference is a candidate, not a decision.
If a remote design is selected, disclose transmission and verify provider policy.
Default persistent audio/transcript retention is none. Research datasets have a
separate approved consent/access/retention plan. See [SECURITY.md](../../SECURITY.md).

## Non-goals and later scope

No accounts, analytics, subscription/payment flow, or native packaging in M0.
The MVP excludes tafsīr/translation libraries, prayer features, social networks,
reader replacement, teacher marketplace, generated recitation, and tajwīd
certification. Daily goals and reminder features are not part of this agreed scope.

Later proposals include other ajzāʾ, multiple reciters, saved memorized ranges,
history, weak-area/adaptive testing, and advanced similar-passage testing. They
need new requirements before implementation.

## Open decisions and approval

Frontend framework, core language, WASM use, recognizer, inference location,
hosting, database, and native packaging remain open. React is not mandatory;
compare frontend options on the same small slice after feasibility. Rust/WASM
are candidates whose value must be measured.

Before implementation, approve the supported recitation convention, data/audio
sources and licenses, reference devices/browsers, numerical accuracy/error
thresholds, cost ceiling, correction/scoring rules, and MVP difficulty scope.
Accepted ADRs record technical decisions. The human owner approves scope and
target changes; agents may propose changes with evidence but not silently lower
requirements. Record approvals in the relevant PR/issue.
