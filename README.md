# Qur’an Ḥifẓ

A focused memorization-testing project: hear an authentic recorded prompt,
continue reciting, and receive honest word-level feedback.

**Status: Phase 0 — governance and research planning.** There is no application,
speech model, or selected technology stack yet. The product specification is a
draft for human review, and benchmark targets are proposals, not measured results.

The first milestone, **M0 — Technical Feasibility**, asks whether real-time Qur’an
recitation tracking can meet acceptable accuracy, latency, privacy, and cost.
Juz 29 is the initial scope. Tajwīd assessment is outside the MVP.

## Project documents

| Document | Purpose |
| --- | --- |
| [PRD v0.1](docs/product/PRD.md) | Product scope, acceptance criteria, and open decisions |
| [NFR-001](docs/requirements/NFR-001.md) | Measurable quality targets and evidence requirements |
| [Agent operating model](AGENTS.md) | Delegation and separation of duties |
| [Contributing](CONTRIBUTING.md) | Tickets, branches, reviews, and human merge gate |
| [Engineering standards](ENGINEERING.md) | Integrity, dependencies, testing, and operations |
| [Security](SECURITY.md) | Reporting and audio/privacy rules |
| [Architecture decisions](docs/architecture/adr/README.md) | Decision process and template |
| [ASR feasibility plan](docs/research/ASR-FEASIBILITY-PLAN.md) | Experiments and initial backlog |
| [Test strategy](docs/testing/TEST-STRATEGY.md) | Acceptance mapping and validation stages |

## Working on this project

Read the PRD, applicable requirements and ADRs, then the engineering and agent
rules before implementation. Work from a traceable ticket on a branch. Changes
require independent review and QA; humans approve product/architecture decisions
and merge PRs. Do not commit directly to `main`.

Phase 0 validation consists of document/link checks and requirements review.
Executable CI enforcement is pending **QA-001**; no tests or checks are claimed
to exist merely because they are described here.

Rust, WASM, frontend framework, speech recognizer, inference location, data
sources, hosting, and database remain unselected. Future code and data licenses
also need explicit decisions; public visibility alone does not grant a license.

## Planning source

These documents adapt the [shared planning conversation](https://chatgpt.com/share/6ac1905c-d320-83ea-af8f-a2816b4cf3b0).
The latest agreed step is a governance-only first PR. Numerical additions and
unresolved choices are identified as proposed or TBD in the relevant document.
