# Agent operating model

## Scope and authority

These rules apply throughout this repository. Human product direction and
approved requirements govern implementation. Read the ticket, the
[PRD](docs/product/PRD.md), applicable NFRs and accepted ADRs, and
[ENGINEERING.md](ENGINEERING.md) before editing. Do not silently change a
requirement, acceptance criterion, test expectation, or architecture to make a
solution easier. Report conflicts with options and evidence.

Phase 0 is documentation only. Do not add application code, datasets, models,
frameworks, or infrastructure under its ticket. Draft product and NFR targets
must be reviewed by the human owner before dependent implementation begins.

## Roles and delegation

| Role | Responsibility | Boundary |
| --- | --- | --- |
| Human owner | Product scope, architectural acceptance, budget, merge authorization | Retains decision authority |
| Lead | Decompose approved work, assign bounded tasks, assemble evidence | Cannot replace independent review with self-review |
| Author | Implement ticket, add appropriate tests, open PR, fix findings | Cannot approve own change |
| Independent reviewer | Derive expectations from requirements/ADRs, then inspect diff | Must use a context separate from author; reports findings rather than editing implementation |
| QA | Independently verify acceptance criteria and regressions | Must use a context separate from author; cannot weaken tests |
| Final approver | Check review resolution, QA, checks, and risks | Separate from author; assess readiness within the human-authorized merge scope |

Use subagents for independent review, QA, and final readiness assessment when
available. Give each the ticket, requirement/ADR paths, scope, and commit or diff
to inspect. Reviewers read requirements before the author's explanation.
Different role labels in the same context are not independent review. If the
runtime cannot provide separate contexts, record the missing gate and leave it
for a human reviewer; do not fabricate completion.

Delegation must identify writable paths and outputs. Avoid simultaneous edits
to the same files; use isolated worktrees when appropriate. Delegates may not
expand scope, publish, merge, alter repository settings, or acquire dependencies
without the authority applicable to the parent task.

## Required workflow

1. Identify stable ticket ID, acceptance criteria, dependencies, and approved scope.
2. Create a scoped branch. The initial branch is `docs/phase-0-governance`.
3. Author changes and run appropriate local checks.
4. Open a PR with requirement links, evidence, limitations, and risks.
5. Independent reviewer inspects requirements, ADRs, and diff; records severity,
   location, impact, and requested outcome for each finding.
6. Author responds with the fix and commit. Reviewer verifies before resolving.
7. QA independently validates acceptance criteria on the current revision.
8. Run applicable CI; final approver checks all evidence against the current head.
9. Human reviews outcomes and merges unless the bounded preauthorization in
   [CONTRIBUTING.md](CONTRIBUTING.md#bounded-merge-preauthorization) applies.
   Within that scope an agent may perform an ordinary PR merge only after the
   independent final readiness assessment and passing CI on the current head.
   Do not enable GitHub auto-merge or change settings under this authorization.

Any substantive update invalidates affected review/QA evidence until rechecked.
Record reviewed commit IDs and agent roles in the PR history. Agent assessments
are not GitHub approvals when they share the PR author's account. Never claim
they satisfy a separate-account branch-protection rule.

## Non-negotiable checks

- The author cannot give final approval to its own PR.
- Never weaken/remove tests or hide failing checks to obtain a pass.
- Architectural changes require an ADR and human acceptance.
- New dependencies require license, security, maintenance, cost, and alternative
  justification; additions affecting architecture also require an ADR.
- Qur’anic text must come from a verified, versioned source; never generate or
  manually rewrite it. Changes require elevated integrity review.
- Normalized comparison text must not overwrite authoritative display text.
- Recognition uncertainty must not be shown as a definite user mistake.
- Audio must follow the approved consent, transmission, and retention policy.
- Acceptance criteria map to tests where possible, or explicit manual evidence.
- Report what actually ran, what passed/failed, and what remains blocked.

See [CONTRIBUTING.md](CONTRIBUTING.md) for severities and merge criteria, and
[TEST-STRATEGY.md](docs/testing/TEST-STRATEGY.md) for phase-specific validation.
