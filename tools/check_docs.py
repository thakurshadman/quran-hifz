"""Offline documentation gate. Run with the pinned tooling in requirements.txt."""

from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

PARSER = MarkdownIt("commonmark").enable("table")
PRD = "docs/product/PRD.md"
NFR = "docs/requirements/NFR-001.md"
TESTS = "docs/testing/TEST-STRATEGY.md"
BACKLOG = "docs/research/ASR-FEASIBILITY-PLAN.md"
REQUIREMENT = re.compile(r"\b(?:FR-\d{3}|NFR-[A-Z]\d{2})(?:/[A-Z]\d{2})*\b")
TICKET = re.compile(r"\b(?:PROD|NFR|ASR|ARCH|HIFZ|QA|SEC)-\d{3}\b")
SECTIONS = {
    "README.md": ["Project documents", "Working on this project", "Planning source"],
    "AGENTS.md": ["Scope and authority", "Roles and delegation", "Required workflow", "Non-negotiable checks"],
    "ENGINEERING.md": ["Decisions and boundaries", "Qur’an and audio integrity", "Code quality and dependencies", "Errors, security, and observability", "Tests and performance", "Ownership and operations"],
    "CONTRIBUTING.md": ["Tickets and branches", "Pull requests", "Definition of done and merge gate", "Releases"],
    "SECURITY.md": ["Reporting", "Audio and user data", "Threat model and release gate"],
    PRD: ["Problem and outcome", "Milestones", "Functional requirements and acceptance criteria", "Quality and success targets", "Data and privacy", "Non-goals and later scope", "Open decisions and approval"],
    NFR: ["Latency and accuracy", "Integrity, reliability, privacy, and security", "Access, compatibility, offline behavior, and cost", "Traceability and change control"],
    TESTS: ["Principles and current state", "Requirements-to-evidence map", "Test layers", "Phase 0 validation", "CI evolution and regression policy"],
    BACKLOG: ["Experiment design", "Measurement protocol and decision gate", "Backlog"],
    "docs/architecture/adr/README.md": [],
    "docs/architecture/adr/ADR-TEMPLATE.md": ["Context and constraints", "Options considered", "Proposed decision and rationale", "Evidence and validation", "Consequences and risks", "Migration, rollback, and review trigger"],
    ".github/pull_request_template.md": ["Problem and resulting behavior", "Requirements and architecture", "Validation", "Impact and risks", "Independent review and QA", "Checklist"],
}
EXPECTED_FR = {f"FR-{n:03}" for n in range(1, 11)}
EXPECTED_NFR = {f"NFR-{group}{n:02}" for group, count in [("L", 3), ("A", 4), ("I", 2), ("R", 2), ("P", 2), ("S", 1), ("U", 1), ("C", 3)] for n in range(1, count + 1)}
EXPECTED_TICKETS = {"PROD-001", "QA-001", "SEC-001", "ARCH-001"} | {f"ASR-{n:03}" for n in range(1, 11)}


def requirement_ids(text: str) -> set[str]:
    result = set()
    for match in REQUIREMENT.finditer(text):
        first, *rest = match.group().split("/")
        result.add(first)
        result.update("NFR-" + tail for tail in rest)
    return result


def inline_text(token) -> str:
    return "".join(child.content for child in token.children or [] if child.type in {"text", "code_inline", "image"})


def heading_slug(text: str) -> str:
    # GitHub-style automatic anchors for the ordinary text headings used here.
    return "".join(c for c in text.lower() if c in "-_ " or not unicodedata.category(c).startswith(("P", "S", "C"))).replace(" ", "-")


class HTMLReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value is None:
                continue
            if key in {"href", "src"}:
                self.links.append(value)
            if key == "id" or (tag == "a" and key == "name"):
                self.anchors.add(value)


class Document:
    def __init__(self, text: str):
        self.text = text
        self.tokens = PARSER.parse(text)
        self.headings: list[tuple[int, str]] = []
        self.anchors: set[str] = set()
        self.links: list[str] = []
        self.rows: list[list[str]] = []
        html = HTMLReferences()
        row = None
        for index, token in enumerate(self.tokens):
            if token.type == "heading_open":
                title = inline_text(self.tokens[index + 1])
                self.headings.append((int(token.tag[1:]), title))
                base = heading_slug(title)
                anchor, suffix = base, 0
                while anchor in self.anchors:
                    suffix += 1
                    anchor = f"{base}-{suffix}"
                self.anchors.add(anchor)
            if token.type == "tr_open":
                row = []
            elif token.type == "tr_close":
                self.rows.append(row)
                row = None
            elif row is not None and token.type == "inline":
                row.append(inline_text(token))
            for child in [token, *(token.children or [])]:
                if child.type == "link_open":
                    self.links.append(child.attrGet("href"))
                elif child.type == "image":
                    self.links.append(child.attrGet("src"))
                elif child.type in {"html_block", "html_inline"}:
                    html.feed(child.content)
        self.links.extend(html.links)
        self.anchors.update(html.anchors)


def check_repository(root: Path, paths: list[str]) -> list[str]:
    errors: list[str] = []
    documents: dict[str, Document] = {}
    for path in sorted(set(paths)):
        if not path.endswith(".md"):
            continue
        target = root / path
        if not target.is_file() or not target.resolve().is_relative_to(root):
            errors.append(f"{path}: missing file or symlink outside repository")
            continue
        try:
            documents[path] = Document(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path}: cannot read UTF-8: {exc}")

    for path, required in SECTIONS.items():
        if path not in documents:
            errors.append(f"{path}: required document missing")
            continue
        doc = documents[path]
        if path != ".github/pull_request_template.md" and sum(level == 1 for level, _ in doc.headings) != 1:
            errors.append(f"{path}: expected exactly one H1 title")
        for section in required:
            if (2, section) not in doc.headings:
                errors.append(f"{path}: required H2 section missing: {section}")

    for path, doc in documents.items():
        if not doc.headings:
            errors.append(f"{path}: document has no heading")
        for destination in doc.links:
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc:
                continue  # Offline gate: external URLs are reviewed manually.
            relative = unquote(parsed.path)
            target = ((root if relative.startswith("/") else (root / path).parent) / relative.lstrip("/")).resolve() if relative else (root / path).resolve()
            if not target.is_relative_to(root):
                errors.append(f"{path}: link escapes repository: {destination}")
                continue
            target_name = target.relative_to(root).as_posix()
            if not target.exists():
                errors.append(f"{path}: broken local link: {destination}")
                continue
            # Existing ignored/untracked assets should not make CI pass locally.
            if target.is_file() and target_name not in paths:
                errors.append(f"{path}: link target is not a repository file: {destination}")
            fragment = unquote(parsed.fragment)
            if fragment and target.suffix == ".md" and target_name in documents and fragment not in documents[target_name].anchors:
                errors.append(f"{path}: missing heading/anchor: {destination}")

    def definitions(path, pattern, expected):
        rows = [row for row in documents.get(path, Document("")).rows if row and pattern.fullmatch(row[0])]
        ids = [row[0] for row in rows]
        for identifier, count in Counter(ids).items():
            if count > 1:
                errors.append(f"{path}: duplicate ID: {identifier}")
        for identifier in sorted(expected - set(ids)):
            errors.append(f"{path}: required ID missing: {identifier}")
        for row in rows:
            if len(row) != 3 or not all(cell.strip() for cell in row):
                errors.append(f"{path}: incomplete definition row: {row[0]}")
        return set(ids), rows

    fr, _ = definitions(PRD, re.compile(r"FR-\d{3}"), EXPECTED_FR)
    nfr, _ = definitions(NFR, re.compile(r"NFR-[A-Z]\d{2}"), EXPECTED_NFR)
    requirements = fr | nfr
    for path, doc in documents.items():
        for identifier in sorted(requirement_ids(doc.text) - requirements):
            errors.append(f"{path}: undefined requirement: {identifier}")
    mapped = set()
    for row in documents.get(TESTS, Document("")).rows:
        if row and requirement_ids(row[0]):
            mapped.update(requirement_ids(row[0]))
            if len(row) != 2 or not row[1].strip():
                errors.append(f"{TESTS}: missing evidence description: {row[0]}")
    for identifier in sorted(requirements - mapped):
        errors.append(f"{TESTS}: requirement lacks evidence mapping: {identifier}")

    tickets, rows = definitions(BACKLOG, TICKET, EXPECTED_TICKETS)
    graph: dict[str, set[str]] = {}
    for row in rows:
        if len(row) != 3:
            continue
        dependencies = set(TICKET.findall(row[2]))
        if not dependencies and row[2] != "None":
            errors.append(f"{BACKLOG}: invalid dependency field: {row[0]}")
        for dependency in sorted(dependencies - tickets):
            errors.append(f"{BACKLOG}: unknown dependency {dependency} in {row[0]}")
        graph[row[0]] = dependencies & tickets
    visiting, visited = set(), set()

    def visit(ticket):
        if ticket in visiting:
            errors.append(f"{BACKLOG}: dependency cycle at {ticket}")
            return
        if ticket in visited:
            return
        visiting.add(ticket)
        for dependency in sorted(graph.get(ticket, set())):
            visit(dependency)
        visiting.remove(ticket)
        visited.add(ticket)

    for ticket in sorted(graph):
        visit(ticket)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        paths = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"], text=True).rstrip("\0").split("\0")
        errors = check_repository(root, paths)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"Documentation check could not run: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"Documentation checks failed: {len(errors)} error(s).", file=sys.stderr)
        return 1
    print(f"Documentation checks passed ({sum(p.endswith('.md') for p in paths)} Markdown files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
