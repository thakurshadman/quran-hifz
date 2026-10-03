# Engineering standards

## Decisions and boundaries

Implement approved, testable requirements in small vertical slices. No stack is
selected by this document. Rust, WASM, React, SvelteKit, Solid, speech providers,
and inference location are candidates; choices require evidence and an accepted
[ADR](docs/architecture/adr/README.md).

Keep authoritative Qur’an data, comparison/alignment logic, speech adapters,
audio capture, and presentation behind explicit interfaces. Recognition yields
revisable hypotheses with confidence/uncertainty; alignment must tolerate partial
updates, repeats, corrections, pauses, and āyah transitions. Specify ordering,
cancellation, backpressure, and end-of-session behavior before implementation.
Public interface or representation changes require compatibility review and an
ADR when architecturally significant.

## Qur’an and audio integrity

- Select authoritative upstream sources and verify terms before importing data.
  Record provenance, edition/recitation convention, version, license, and checksum.
- Store immutable display text separately from derived comparison forms. Make
  transformations versioned and reproducible, retaining stable word/āyah IDs.
- Validate counts, boundaries, mappings, and checksums against the selected
  source/convention, not unexamined assumptions about all editions.
- Never generate Qur’anic text or prompt recitation with an LLM/TTS system.
- Prompt recordings require reciter identity, source, license, checksum, and
  validated āyah/word timing metadata appropriate to the cue granularity.
- Dataset, normalization, and timing changes require an independent technical
  review plus a qualified Qur’an-content reviewer designated by the human owner.
  A software agent's approval does not replace content expertise.

## Code quality and dependencies

Use clear domain names, small interfaces, explicit types, and documented invariants.
Select formatter/linter/toolchain versions after language decisions; CI must use
the same pinned configuration as local development. For Rust, evaluate rustfmt,
clippy, unit/property tests; for TypeScript, select formatter/linter, type checking,
and test tooling. These are future gates, not currently installed tools.

Every new dependency needs purpose, alternatives, license compatibility,
maintenance/security review, version/update policy, and size/runtime/cost impact.
Commit lockfiles when the chosen ecosystem supports them. Prefer narrow,
replaceable dependencies. Record model and dataset licenses separately from code.
Do not assume public data is licensed for redistribution or model training.

## Errors, security, and observability

Handle denied microphone permission, device loss, network/provider failure,
timeouts, and stale results explicitly. No crash or unavailable recognition may
be scored as an incorrect recitation. Stop capture and release resources when
the session ends. Retry only with bounds, cancellation, and safe idempotency.

Log event types, durations, version IDs, and sanitized error categories, not raw
audio, transcripts, Qur’an/user text payloads, tokens, or personal identifiers.
Debug capture requires a separately approved consent/retention workflow; never
enable it silently. Use monotonic clocks for latency and measure p50/p95/p99
under declared device/network conditions.

Treat transcripts, imported metadata, model output, and external content as
untrusted data. Validate lengths/types; avoid executable interpretation and HTML
injection. Keep secrets server-side where applicable and out of git/logs. Follow
[SECURITY.md](SECURITY.md) and [NFR-001](docs/requirements/NFR-001.md).

## Tests and performance

Follow the [test strategy](docs/testing/TEST-STRATEGY.md). Derive tests from
requirements, not just implementation. Use deterministic seeds/clocks, immutable
golden fixtures, and explicit tolerances. Do not modify expected results simply
to accommodate a regression. Justify fixture updates with provenance and review.

Benchmark alignment independently of speech inference, and measure the actual
end-to-end path. Report startup/model-download costs separately from steady-state
latency. Measure resource use and inference cost; do not extrapolate an unlabelled
single-device result into a product claim.

## Ownership and operations

The human repository owner assigns technical and Qur’an-content reviewers;
none are assumed assigned by this document. Agents own bounded tasks, not merge
authority. Before production, document service ownership, alerting, deployment,
rollback, data deletion, incident response, and recovery procedures. Hosting and
CI provider selection require their own decisions. No deployment is included in
Phase 0.
