"""Seed defects in an isolated copy of the real documentation; never edit sources."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from check_docs import BACKLOG, NFR, PRD, TESTS, check_repository

ROOT = Path(__file__).resolve().parents[1]


class DocumentationRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"], text=True).rstrip("\0").split("\0")
        for name in self.paths:
            source = ROOT / name
            if source.is_file():
                destination = self.root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)

    def append(self, path, text):
        with (self.root / path).open("a", encoding="utf-8") as handle:
            handle.write("\n" + text + "\n")

    def replace(self, path, old, new):
        target = self.root / path
        text = target.read_text(encoding="utf-8")
        self.assertIn(old, text, "Seed no longer matches the specification")
        target.write_text(text.replace(old, new, 1), encoding="utf-8")

    def assert_failure(self, message):
        errors = check_repository(self.root, self.paths)
        self.assertTrue(any(message in error for error in errors), errors)

    def test_repository_passes(self):
        self.assertEqual(check_repository(self.root, self.paths), [])

    def test_missing_document(self):
        (self.root / "SECURITY.md").unlink()
        self.assert_failure("required document missing")

    def test_missing_required_section(self):
        self.replace(PRD, "## Open decisions and approval", "## Renamed")
        self.assert_failure("required H2 section missing: Open decisions and approval")

    def test_duplicate_title(self):
        self.append(PRD, "# Duplicate title")
        self.assert_failure("expected exactly one H1")

    def test_broken_inline_link(self):
        self.append("README.md", "[missing](docs/missing.md)")
        self.assert_failure("broken local link")

    def test_broken_reference_link(self):
        self.append("README.md", "[missing][source]\n\n[source]: docs/missing.md")
        self.assert_failure("broken local link")

    def test_broken_image(self):
        self.append("README.md", "![missing image](docs/missing.png)")
        self.assert_failure("broken local link")

    def test_broken_heading(self):
        self.append("README.md", "[missing](docs/product/PRD.md#absent)")
        self.assert_failure("missing heading/anchor")

    def test_missing_html_target(self):
        self.append("README.md", '<a href="docs/missing.md">missing</a>')
        self.assert_failure("broken local link")

    def test_external_and_code_examples_are_not_fetched(self):
        self.append("README.md", "[external](https://invalid.example/not-checked)\n\n```md\n[example](missing.md)\n```\n\n`[example](missing.md)`")
        self.assertEqual(check_repository(self.root, self.paths), [])

    def test_valid_anchors_references_encoded_paths_and_duplicate_headings(self):
        self.append("README.md", "## Repeated\n## Repeated\n## Repeated-1\n<a id=\"custom\"></a>\n[one](#repeated) [two](#repeated-1) [three](#repeated-1-1) [custom](#custom)\n[ref][product]\n\n[product]: docs/product/%50RD.md#open-decisions-and-approval\n[root](/SECURITY.md#reporting)")
        self.assertEqual(check_repository(self.root, self.paths), [])

    def test_escaping_link(self):
        self.append("README.md", "[outside](../outside.md)")
        self.assert_failure("link escapes repository")

    def test_untracked_target(self):
        (self.root / "untracked.txt").write_text("not committed")
        self.append("README.md", "[untracked](untracked.txt)")
        self.assert_failure("link target is not a repository file")

    def test_removed_requirement(self):
        self.replace(PRD, "| FR-010 |", "| changed |")
        self.assert_failure("required ID missing: FR-010")

    def test_duplicate_requirement(self):
        self.replace(PRD, "| FR-010 |", "| FR-009 |")
        self.assert_failure("duplicate ID: FR-009")

    def test_incomplete_requirement(self):
        self.replace(PRD, "| FR-001 | Select known material |", "| FR-001 | |")
        self.assert_failure("incomplete definition row: FR-001")

    def test_undefined_requirement_reference(self):
        self.append("README.md", "See FR-999 and NFR-A99.")
        self.assert_failure("undefined requirement: FR-999")
        self.assert_failure("undefined requirement: NFR-A99")

    def test_removed_evidence_mapping(self):
        self.replace(TESTS, "FR-001, FR-002, FR-009", "FR-002, FR-009")
        self.assert_failure("requirement lacks evidence mapping: FR-001")

    def test_compressed_evidence_mapping(self):
        self.replace(TESTS, "NFR-A01/A02/A03", "NFR-A01/A02")
        self.assert_failure("requirement lacks evidence mapping: NFR-A03")

    def test_empty_evidence_description(self):
        target = self.root / TESTS
        text = target.read_text()
        row = next(line for line in text.splitlines() if line.startswith("| FR-001,"))
        self.replace(TESTS, row, "| FR-001, FR-002, FR-009 | |")
        self.assert_failure("missing evidence description")

    def test_missing_backlog_id(self):
        self.replace(BACKLOG, "| QA-001 |", "| changed |")
        self.assert_failure("required ID missing: QA-001")

    def test_unknown_dependency(self):
        self.replace(BACKLOG, "| ASR-010 human go decision |", "| ASR-999 human go decision |")
        self.assert_failure("unknown dependency ASR-999")

    def test_dependency_cycle(self):
        self.replace(BACKLOG, "| None |", "| ARCH-001 |")
        self.assert_failure("dependency cycle")

    def test_self_dependency(self):
        self.replace(BACKLOG, "| None |", "| PROD-001 |")
        self.assert_failure("dependency cycle at PROD-001")

    def test_invalid_dependency(self):
        self.replace(BACKLOG, "| None |", "| pending |")
        self.assert_failure("invalid dependency field")

    def test_symlink_outside_repository(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "external.txt"
            target.write_text("outside")
            (self.root / "linked.txt").symlink_to(target)
            self.paths.append("linked.txt")
            self.append("README.md", "[outside](linked.txt)")
            self.assert_failure("link escapes repository")

    def test_ci_whitespace_command_rejects_seeded_commit(self):
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        git = ["git", "-C", str(self.root)]
        commit = git + ["-c", "user.name=Regression Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m"]
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(commit + ["Baseline"], check=True)
        self.append("README.md", "Seeded trailing whitespace.  ")
        subprocess.run(git + ["add", "README.md"], check=True)
        subprocess.run(commit + ["Seed whitespace defect"], check=True)
        result = subprocess.run(git + ["diff", "--check", "HEAD^", "HEAD"], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trailing whitespace", result.stdout)

    def test_cli_nonzero_for_seeded_failure(self):
        self.append("README.md", "[seeded failure](missing.md)")
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        result = subprocess.run([sys.executable, str(ROOT / "tools/check_docs.py"), "--root", str(self.root)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("broken local link", result.stderr)


if __name__ == "__main__":
    unittest.main()
