# Test strategy

## Principles and current state

Derive tests from the [PRD](../product/PRD.md) and
[NFR-001](../requirements/NFR-001.md), independently of implementation.
No executable product tests exist in Phase 0. This document defines future
coverage and the checks applicable to the governance PR; it is not a test report.

Use fixed seeds/clocks and versioned fixtures for deterministic logic. Speech
quality needs labelled held-out audio and statistical evidence, not assertions
that one model transcript matches itself. Preserve authoritative Qur’an display
text and separate comparison representations in all fixtures.

## Requirements-to-evidence map

| Requirement | Planned evidence |
| --- | --- |
| FR-001, FR-002, FR-009 | Unit/property tests for valid scoped selection and seeded determinism; audio cue boundary/content review; invalid/empty scope and end-of-scope cases |
| FR-003, NFR-P01, NFR-R01 | Integration/E2E permission, capture indicator, stop/cancel/navigation/device-loss tests; network/storage/log audit |
| FR-004, FR-007, NFR-A04 | Golden state transitions and property tests across stream chunk boundaries, late/duplicate revisions, backtracking, repeated/self-corrected words, pauses and finalization |
| FR-005, NFR-A01/A02/A03 | Deterministic alignment fixtures plus independently annotated held-out benchmark; measure error precision/recall, false accusations, false acceptance and uncertainty |
| FR-006, FR-008 | UI/E2E tentative-versus-final feedback, provider failure without grading, result/next-question reset, correction/replay races |
| FR-010, NFR-I01/I02 | Provenance/license/checksum review, import validation, immutable-display tests, ID/timing boundary fixtures and qualified content review |
| NFR-L01/L02/L03, NFR-R02 | Instrumented stage and end-to-end p50/p95/p99 benchmarks, warm/cold paths, resource/soak tests on declared devices/networks |
| NFR-P02, NFR-S01 | Consent/retention/withdrawal review, threat-model checks, malicious input tests, secret/dependency checks appropriate to selected stack |
| NFR-U01, NFR-C01/C02 | Manual and automated accessibility, Arabic RTL, keyboard/screen reader, browser/device matrix and offline/failure-mode tests |
| NFR-C03 | Reproducible measured cost/session model, scenario assumptions and sensitivity against the approved ceiling |

## Test layers

- **Unit:** normalization, identifiers, boundaries, prompt selection, and state
  transitions. No test should require network access for deterministic logic.
- **Property:** no panic on valid/bounded malformed input; stable IDs/display
  text; invariant-preserving revisions; convergence for equivalent finalized
  hypothesis streams under supported chunking, with time-dependent behavior
  controlled by a test clock.
- **Golden:** known recitations and annotated expected word/error events. Record
  consent/license and source versions; restricted recordings stay outside git.
- **Integration:** microphone → recognizer adapter → alignment → UI; any accepted
  WASM/API boundary; cancellation, backpressure, errors and resource cleanup.
- **End-to-end:** select Juz 29/sūrahs, play authentic cue, continue through a
  fake deterministic stream, view result, start next question. Add licensed audio
  replay and real-device manual checks for the actual capture path.
- **Performance/security/accessibility:** explicit NFR evidence, not inferred from
  unit-test success. Keep expensive/nondeterministic benchmarks separate from
  fast PR checks and require their results for affected model/performance changes.

Mocks test contracts and failure paths; they cannot prove recognizer accuracy,
browser microphone behavior, authentic prompt content, or remote retention policy.

## Phase 0 validation

Verify the agreed 12-file scope, relative links, required content, requirement
traceability, consistent draft status, absence of silent technology decisions,
and separation of duties. Run `git diff --check` and a relative-link existence
check. Independently review source-to-document fidelity and open gates. Record
commands/results and the exact reviewed commit in the PR.

No Rust/TypeScript build, model benchmark, or application E2E test is applicable
yet. QA-001 adds the executable checks and seeded regressions described in
[DOCUMENTATION-CI.md](DOCUMENTATION-CI.md). Passing CI does not prove that branch
protection is enforced; the proposed protection and configuration evidence remain
an explicit external gate.

## CI evolution and regression policy

QA-001 introduces executable document checks first. Add formatting, linting,
type checking, unit/property tests, integration/E2E, dependency/security audits,
build and any WASM tests as the corresponding stack/code is accepted. Require
appropriate gates before production merges; report unavailable checks honestly.

For every defect, add the smallest useful regression case. Never delete/weaken
a test or widen thresholds just to pass CI. Fixture/expectation changes require
specification/source evidence and independent review. Quarantining flaky tests
requires a tracked issue, owner, reason, expiry and explicit release impact;
quarantined checks do not count as passes.

QA derives expectations separately from the author's tests and reports failures,
limitations and manual checks. Recheck affected evidence after changes. The final
approver verifies current-revision results and unresolved findings. Merge execution
follows the human authorization in [CONTRIBUTING.md](../../CONTRIBUTING.md#bounded-merge-preauthorization).
