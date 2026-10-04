# Documentation checks and protection proposal

**Ticket:** QA-001, following merged PROD-001 / PR #15.
**Scope:** documentation tooling only; no application stack is selected.

## Local commands

Use CPython **3.12.14**, also pinned in [.python-version](../../.python-version).
From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r tools/requirements.txt
git add <your-intended-files>
.venv/bin/python tools/check_docs.py
.venv/bin/python -m unittest discover -s tools -p 'test_*.py' -v
git diff --check
git diff --cached --check
```

Confirm `python3.12 --version` is the pinned patch before creating the environment.
On Windows, use `.venv\Scripts\python.exe` instead. The checker reads tracked/staged
paths from `git ls-files`; stage intended new files before running it. It never
fetches linked URLs. Its exit code is 0 for success, 1 for validation failure,
and 2 if the check cannot run. Diagnostics name the source file and defect.

## Automated coverage and limits

[check_docs.py](../../tools/check_docs.py) uses a CommonMark parser with table
support, rather than extracting Markdown links with regular expressions. It checks:

- The 12 governance documents, their required H2 sections and one H1 title
  (the PR template uses H2 headings); additional Markdown files need a heading.
- Relative/root-relative Markdown links, images, resolved reference-style links,
  and HTML `href`/`src`; files must exist in the repository. Paths cannot escape
  the checkout, including through symlinks. Percent-encoded paths are decoded.
- Markdown heading fragments, repeated-heading suffixes, and explicit HTML anchors.
- Required stable FR/NFR IDs, uniqueness, nonempty definition/acceptance cells,
  unknown references and evidence-map coverage, including abbreviated NFR lists.
- Required backlog IDs, nonempty deliverable/dependency cells, known dependencies,
  and an acyclic dependency graph (including rejection of self-dependencies).

The [regression suite](../../tools/test_check_docs.py) copies real documents into
a temporary directory and seeds missing documents/sections, broken link forms,
missing anchors, duplicate/missing IDs, missing evidence, and dependency defects.
It also runs the CLI with a seeded broken link and asserts a nonzero exit, and
commits a trailing-whitespace defect in a temporary repository to prove CI's Git
whitespace command rejects it. The suite also parses all workflow YAML with
PyYAML's non-executing BaseLoader and rejects a seeded unquoted-colon command.
This catches YAML syntax errors locally; it does not validate GitHub Actions'
schema, expression semantics, action availability, or runner behavior. Live
GitHub CI remains a required gate. Positive
cases cover valid references, anchors, encoded paths, and ignored code examples.

These checks prove structural consistency, not correctness of prose, sufficiency
of acceptance criteria, benchmark success, human approval, or semantic fulfillment
of a dependency. External links and non-Markdown fragments need manual review.
Unresolved Markdown reference labels are ordinary CommonMark text and are not
reported as links. Heading anchors support ordinary GitHub-style text headings;
exotic renderer extensions, embedded HTML headings, and Unicode symbol edge cases
need manual review. No product tests or ASR measurements are claimed.

The stable required-check name is **Documentation checks** from
[documentation.yml](../../.github/workflows/documentation.yml). It runs on every
pull request, push to `main`, and manual dispatch, with no path filter or conditional
skip. CI runs the same checker/tests plus `git diff --check HEAD^ HEAD`; checkout
fetches two commits so this checks the PR merge against its base or a main push
against its previous commit. CI failure remains a merge blocker.

The workflow grants only `contents: read`, disables persisted checkout credentials,
uses immutable action commits and a five-minute timeout, and neither references
secrets nor uses `pull_request_target`. GitHub-hosted Ubuntu 24.04 is a mutable
runner image; package hashes and exact tool versions pin our tools, not that OS
image or all of GitHub's execution infrastructure.

## Tool choice and maintenance

Python is used only for lightweight offline documentation validation. Alternatives
were a hand-written Markdown parser (fragile for code blocks/reference links) or
a separate Node/Rust toolchain (unnecessary runtime for this scope). The standard
library supplies tests, file/URL handling, and the dependency graph. No product
framework, hosting provider, model, service, or paid dependency is introduced.

- **CPython 3.12.14:** PSF license; exact patch aligns local/CI runtimes. Version
  changes require the checker regressions and review.
- **markdown-it-py 4.2.0:** MIT; maintained by Executable Books. PyPI records this
  release on 2026-05-07; the installed distribution's MIT license was inspected.
  Parses CommonMark and tables without executing documentation content.
- **mdurl 0.1.2:** MIT; the parser's narrow URL helper dependency. Its older stable
  release requires periodic advisory/compatibility review; age alone is not proof
  of security. Neither library ships in a product runtime. Only their default
  dependencies are installed, using wheel-only installation with SHA-256 hashes.
- **PyYAML 6.0.3:** MIT, maintained by the YAML/PyYAML project; PyPI records
  the release on 2025-09-25. Added after GitHub rejected an unquoted colon in
  a workflow command that the Markdown tests could not detect. BaseLoader parses
  syntax without constructing Python objects; a hand-written YAML check would
  repeat the parser fragility this gate avoids. No additional runtime dependencies
  are required. Wheel-only hashed installation avoids source builds. Review
  advisories and wheel/runtime compatibility when updating it.
- **actions/checkout v7.0.1** and **actions/setup-python v7.0.0:** MIT, maintained
  by GitHub, use Node 24. Release tags were resolved through GitHub's API to the
  full commit SHAs recorded in the workflow, not copied from an assumed version.

Dependencies execute with CI's read-only credential scope. Markdown remains
untrusted input; parsing does not evaluate code or contact link destinations.
This is a bounded dependency review, not a claim that no vulnerabilities exist.
There is no project license selected yet; MIT/PSF permit this development-tool use
subject to their notices, which remain included in installed distributions. Review
licensing again before redistributing tools with a product. No recurring service
is purchased; CI remains subject to the repository owner's GitHub Actions plan.

[requirements.in](../../tools/requirements.in) records the direct requirement;
[requirements.txt](../../tools/requirements.txt) pins all three resolved dependencies
and artifact hashes. To regenerate intentionally, use **uv 0.12.19**:

```sh
uv pip compile tools/requirements.in --generate-hashes --output-file tools/requirements.txt
```

`uv` generated the lock and is not required for ordinary checks or CI. Update
versions/hashes/actions in a reviewed PR after checking upstream releases,
licenses/advisories and compatibility. Re-run all regressions; do not auto-update
pins without review. The author/lead proposing an update owns this evidence until
the human owner assigns ongoing maintenance. Review pins before future tooling
changes and after relevant security advisories.

## Proposed repository protection

This is a proposal, not an applied setting. Read-only API inspection during QA-001
reported `main` as `protected: false`, enforcement `off`, no required contexts,
and an empty rulesets list. The detailed classic-protection and Actions-permissions
endpoints returned 403, so their inaccessible configuration details are unknown.
Repository `allow_auto_merge` was false. No setting is changed by this PR.

Suggested configuration for `main`, after the first successful check is visible:

1. Require pull requests and the **Documentation checks** status from GitHub Actions.
2. Require the branch to be up to date before merging, or separately validate any
   future merge-queue setup. This workflow does not currently target merge groups.
3. Require conversation resolution, block force pushes and deletion, and disallow
   routine admin/bypass merges. Preserve the audit trail and reviewed commit.
4. Require one independent GitHub approval once a separate reviewer account is
   available; dismiss stale approvals and require approval of the most recent
   reviewable push. Same-account agent evidence cannot satisfy this rule. Until
   configured, record that independent agent review is a manual gate only.

The repository owner must supply configuration evidence (settings screenshot or
readable API response showing active checks/approval policy) and validate rejection
of a PR with a failing/missing check before marking protection enforcement complete.
An owner may explicitly accept a documented interim manual gate for this bounded
bootstrap PR, but that does not satisfy production-feature protection readiness.
**Keep QA-001's protection-evidence gate open until this evidence exists**; passing
CI and merging the tooling alone must not be called complete enforcement.

Merge execution follows [CONTRIBUTING.md](../../CONTRIBUTING.md#bounded-merge-preauthorization):
a separate final readiness assessment, passing GitHub CI and current-head review/QA,
with an expected-head SHA guard. This authorization does not turn on GitHub's
auto-merge setting. Draft product/quality targets remain unapproved.

## Rollback

Revert the tooling PR through a reviewed PR if it blocks valid documentation.
Investigate parser/fixture defects with a regression before changing a check.
Do not disable a required check or remove evidence merely to merge a failing PR.
If protection is configured later, coordinate any check-name migration so required
statuses never become permanently pending. This change has no application/data
migration, deployment, or audio behavior to roll back.
