# Architecture decision records

No architectural decisions are accepted yet. Candidate technologies mentioned in
planning are not commitments.

Use [ADR-TEMPLATE.md](ADR-TEMPLATE.md) and the next available `ADR-NNN-short-title.md`.
Assign IDs once; retain superseded records. Statuses are **Proposed**, **Accepted**,
**Rejected**, and **Superseded**. Authors may propose; independent review and human
acceptance are required to change status to Accepted. Link approval evidence.

Record context, requirements, options including simpler/no-change alternatives,
measurements, tradeoffs, security/privacy, integrity, cost, consequences, and
reversal/migration strategy. A superseding ADR links both directions. Do not
rewrite historical rationale to make an old decision look different.

Expected decision topics after M0 include recognition/inference architecture,
Qur’an text/audio provenance and conventions, privacy model, core/alignment
language, frontend framework, WASM boundary if justified, and deployment.
Public API, trust-boundary, persistent representation, or significant dependency
changes also need an ADR. Routine local choices can be explained in the PR.
