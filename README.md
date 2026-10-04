# Qur’an Ḥifẓ

A focused memorization-testing project: hear an authentic recorded prompt,
continue reciting, and receive honest word-level feedback.

**Status: early speech experiments.** A small Al-Ikhlas transcription prototype
and a reproducible model-comparison harness exist. The full memorization app and
its production stack are not selected. Product targets remain proposals; one
recording is not evidence that the full benchmark targets have been met.

The first milestone, **M0 — Technical Feasibility**, asks whether real-time Qur’an
recitation tracking can meet acceptable accuracy, latency, privacy, and cost.
Juz 29 is the initial scope. Tajwīd assessment is outside the MVP.

## Project documents

| Document | Purpose |
| --- | --- |
| [PRD v0.1](docs/product/PRD.md) | Product scope, acceptance criteria, and open decisions |
| [NFR-001](docs/requirements/NFR-001.md) | Measurable quality targets and evidence requirements |
| [Agent operating model](AGENTS.md) | Delegation and separation of duties |
| [Contributing](CONTRIBUTING.md) | Tickets, branches, reviews, and bounded merge authorization |
| [Engineering standards](ENGINEERING.md) | Integrity, dependencies, testing, and operations |
| [Security](SECURITY.md) | Reporting and audio/privacy rules |
| [SEC-001 pilot policy](docs/security/SEC-001.md) | Practical privacy safeguards for the owner and a few known people |
| [Architecture decisions](docs/architecture/adr/README.md) | Decision process and template |
| [ASR feasibility plan](docs/research/ASR-FEASIBILITY-PLAN.md) | Experiments and initial backlog |
| [Reproduce the model comparison](benchmarks/recitation/README.md) | Setup, pinned models, scoring, timing, privacy and tests |
| [Exploratory comparison results](benchmarks/recitation/RESULTS.md) | Four models on one private Al-Ikhlas clip, with limitations |
| [Test strategy](docs/testing/TEST-STRATEGY.md) | Acceptance mapping and validation stages |

## Working on this project

Read the PRD, applicable requirements and ADRs, then the engineering and agent
rules before implementation. Work from a traceable ticket on a branch. Changes
require independent review and QA; humans approve product/architecture decisions
and authorize merges. Bounded low-risk documentation/tooling PRs may be merged
by an agent under [CONTRIBUTING.md](CONTRIBUTING.md#bounded-merge-preauthorization).
Do not commit directly to `main`.

Documentation tooling validates local links, document structure, requirements
traceability, and backlog dependencies. Run the [local checks](docs/testing/DOCUMENTATION-CI.md#local-commands)
before a PR. The same checks and seeded regressions run in GitHub Actions.
Required-check/approval protection is proposed, not configured by these files;
see the [current evidence and remaining gate](docs/testing/DOCUMENTATION-CI.md#proposed-repository-protection).

Rust, WASM, frontend framework, speech recognizer, inference location, data
sources, hosting, and database remain unselected. Future code and data licenses
also need explicit decisions; public visibility alone does not grant a license.

## Planning source

These documents adapt the [shared planning conversation](https://chatgpt.com/share/6ac1905c-d320-83ea-af8f-a2816b4cf3b0).
Phase 0 governance was merged in PR #15; QA-001 adds documentation CI. Numerical additions and
unresolved choices are identified as proposed or TBD in the relevant document.
