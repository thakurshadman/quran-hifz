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
- Human owner approves product/architecture changes. Merge execution follows
  the bounded preauthorization below, or remains with the human owner.

For the governance-only bootstrap PR, document/link validation and independent
requirements review are the applicable checks. There is no runtime to build/test.
**QA-001** adds executable CI; repository protection configuration remains a
separate pending gate before production feature work is merged. These documents
do not configure rulesets or required approvals. The lead/final approver must
verify the documented gates manually before any authorized merge and report the
absence of platform enforcement. See the [CI and protection proposal](docs/testing/DOCUMENTATION-CI.md).

Do not add package-manager files or empty CI jobs merely to suggest enforcement.
Later language-specific checks must match accepted ADRs and actual code.

## Bounded merge preauthorization

The human owner explicitly authorized continued work and risk-based agent merges
in the conversation following PR #15. This permits an ordinary PR merge for
bounded, reversible documentation and documentation-tooling changes, including
QA-001, once **all** of these conditions hold:

- Independent reviewer and QA each assess the final revision as low risk; the
  independent final approver records readiness and the reason for that risk rating.
- Acceptance evidence is complete for the scope being merged, applicable local
  checks and GitHub CI pass on the exact current PR head, and no BLOCKER or MAJOR
  finding remains. Any explicitly deferred external configuration gate stays open.
- Review/QA records identify the evaluated commit; changes invalidate affected
  evidence. Recheck the PR head and base/mergeability before merging, and use an
  expected-head SHA guard. A changed head must be reviewed and checked again.
- No self-approval, direct push to `main`, force push, admin bypass, disabling
  checks, or representing same-account agent reviews as GitHub approvals.
  Respect any configured GitHub protections, including separate-account approval.

This authorization excludes architecture decisions, application dependencies,
Qur’an text/data/recordings, audio/privacy behavior, paid services, and releases.
Human decisions for these areas and draft PRD/NFR targets remain pending. Routine
docs-only tool updates require the same dependency justification and review gates.
The narrow policy edit recording this explicit authorization is in QA-001's scope;
future edits expanding merge authority or weakening safeguards are **not**
automatically low risk or preauthorized. If risk is uncertain, report the unresolved
gate and leave the PR open for a human decision.

This permits an agent to execute a reviewed merge; it does not enable GitHub's
repository auto-merge feature or authorize changing repository settings.

## Local documentation checks

Follow [DOCUMENTATION-CI.md](docs/testing/DOCUMENTATION-CI.md#local-commands).
Stage new files so the checker includes them; it intentionally checks the Git
index file list. Product test suites remain future work under accepted ADRs.

## Releases

Before the first application release, define semantic versioning, changelog,
staging smoke tests, migrations, release approval, monitoring, and rollback in a
release ticket. Research outputs must identify data/model versions and reproduce
their measurements. A successful experiment is not a production release.
