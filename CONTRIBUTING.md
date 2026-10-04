# Contributing

## Tickets and branches

Every change has a stable ID, problem statement, acceptance criteria, dependencies,
and validation plan. The [initial backlog](docs/research/ASR-FEASIBILITY-PLAN.md)
uses `PROD`, `NFR`, `ASR`, `ARCH`, `HIFZ`, `QA`, and `SEC` prefixes. GitHub issue
numbers supplement these IDs; they do not replace them.

Use scoped branches such as `feature/HIFZ-001-description`,
`research/ASR-001-description`, `fix/HIFZ-001-description`, or
`docs/ARCH-001-description`. Phase 0 uses `docs/phase-0-governance`.
Keep commits focused; use an imperative subject with a conventional type such as
`docs: establish Phase 0 governance`. Do not push directly to `main` or rewrite
another contributor's history.

## Pull requests

Use the [PR template](.github/pull_request_template.md). Explain the problem and
resulting behavior, cite requirements/ADRs, and show relevant validation.
Unimplemented requirements and failed/unavailable checks must be explicit.
Use draft status while mandatory evidence is incomplete.

The author, independent reviewer, QA, and final approver follow
[AGENTS.md](AGENTS.md). Reviewers first read requirements and ADRs, then the diff.
Findings remain in PR history, with severity, file/line, impact, requested outcome,
author response, fix commit, and verification. Only the reviewer resolves their
finding after verification. If unavailable, an independent human replacement
must document the reason and verification.

| Severity | Meaning and disposition |
| --- | --- |
| BLOCKER | Correctness, security, privacy, Qur’an integrity violation, or weakened tests: must be fixed before merge |
| MAJOR | Architecture, reliability, or material coverage gap: fix before merge; any exception needs explicit human rationale, tracked follow-up, and no breach of a non-negotiable rule |
| MINOR | Fix or document why it is deferred with reviewer agreement |
| NIT | Optional readability/style suggestion |
| QUESTION | Resolve uncertainty; escalate to the relevant severity if it reveals a defect |

Unverified Qur’an sources, normalization that changes display text, unsupported
certainty in feedback, and unapproved audio retention are BLOCKER findings.

## Definition of done and merge gate

- Acceptance criteria are satisfied and traced to evidence.
- Independent review and QA cover the current revision; all required findings
  are resolved. Final readiness assessment is independent of the author.
- Applicable automated checks pass; no skipped or absent check is represented as
  passing. New dependencies and architectural changes have required justification.
- Documentation, security/privacy assessment, performance evidence, and rollback
  notes are updated where relevant.
- Human owner approves product/architecture changes and performs the merge.

For the governance-only bootstrap PR, document/link validation and independent
requirements review are the applicable checks. There is no runtime to build/test.
**QA-001** must establish executable CI and check enforcement before production
feature work is merged. Repository rulesets and required approvals are not
configured by these documents. Until configured, the human owner enforces these
gates manually; agents must accurately report this limitation.

Do not add package-manager files or empty CI jobs merely to suggest enforcement.
Later language-specific checks must match accepted ADRs and actual code.

## Releases

Before the first application release, define semantic versioning, changelog,
staging smoke tests, migrations, release approval, monitoring, and rollback in a
release ticket. Research outputs must identify data/model versions and reproduce
their measurements. A successful experiment is not a production release.
