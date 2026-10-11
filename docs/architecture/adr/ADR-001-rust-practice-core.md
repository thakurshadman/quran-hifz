# ADR-001 — Rust core for personal practice

- Status: Accepted for the personal practice implementation; accuracy and release qualification remain open
- Date: 2026-10-11
- Requirement/ticket IDs: HIFZ-001, ASR-004, ASR-007; PRD FR-003/005/006/008/010
- Human decision: the owner instructed, “Just auto handle everything. Let me know when the full app is done. Use rust as language.” This accepts Rust and delegates routine implementation choices; it does not establish model accuracy or content expertise.
- Independent reviewers: technical, QA and readiness assessments are recorded in the implementation PR

## Decision

Write passage selection, normalization and tentative word comparison in Rust.
Compile the same library to WebAssembly for the browser. Small JavaScript adapters
handle browser controls, the microphone and the existing local Tilawi model.
This is real Rust execution, not a separate unused Rust example.

Use the existing static website build. No backend, account database or remote
speech service is needed. The existing native Node benchmark remains separate.
Rust cannot make a speech model hear a missing sound more reliably by itself.

## Alternatives and tradeoffs

Keeping all logic in JavaScript would have the smallest build setup, but would
not meet the owner's language choice. A full Rust UI framework would add a second
large migration without improving recognition. A Rust server would require
hosting and potentially sending audio off the device. The small Rust/WASM core
keeps capture local and is testable on both native Rust and browser builds.

Rust 1.90.0 and Cargo.lock pin the build. wasm-bindgen 0.2.104 bridges Rust to the
browser; serde/serde_json handle bounded JSON; unicode-normalization preserves
Unicode equivalence. These maintained libraries are MIT/Apache-2.0, with Rust's
usual dual-license choices. Exact package licenses and versions are available
through `cargo metadata --locked`. The build-only wasm-bindgen CLI uses the same
version and its own locked dependencies. Its old development-server dependencies
are not shipped in the app. No inference service fees are added.

## Scope and honest limits

The personal flow supports Juz 29, Al-Fatiha and Al-Ikhlas; bounded verse ranges;
a verbatim first-verse text cue; local capture; tentative feedback; retry and next
passage. It does not claim the original full MVP is complete: authentic licensed
audio prompts, live partial recognition, self-correction windows, difficulty
levels, held-out accuracy and physical-phone qualification remain open.

The comparison keeps the earlier conservative rules: ambiguous or substituted
words make the result unsure. No score or pronunciation judgement is produced.
The pinned source is unchanged and hash-checked; display text is never normalized.
Qualified content review is still not supplied by software tests or agent review.

## Verification and rollback

Run native Rust tests, the original word-comparison tests through compiled WASM,
and browser lifecycle/range tests. CI also builds the static app. Review the PR
for exact results and remaining gates; passing software tests is not an accuracy
benchmark. The README describes source verification and private-audio handling.

Revert the implementation PR to restore the earlier experiment. Revisit this
choice if WASM startup, device memory, or integration costs outweigh its benefits.
