"""Synthetic sound groups only: no reference text, recordings or model inference."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import omission_probe as probe


class AlignmentTests(unittest.TestCase):
    def align(self, hypothesis):
        return probe.align_window(list("ABCDEFGH"), list(hypothesis), 3, 5)

    def test_exact_control_with_unrelated_prefix_and_suffix(self):
        result = self.align("XYZABCDEFGHXYZ")
        self.assertEqual(result["status"], "no_target_difference")
        self.assertEqual(result["edit_cost"], 0)
        self.assertEqual(result["target_operations"],
                         {"match": 2, "delete": 0, "substitute": 0, "insert": 0})

    def test_partial_target_deletion_is_only_possible_omission(self):
        for hypothesis in ("ABCEFGH", "ABCDFGH"):
            with self.subTest(hypothesis=hypothesis):
                result = self.align(hypothesis)
                self.assertEqual(result["status"], "possible_omission")
                self.assertEqual(result["context_edits"], 0)
                self.assertEqual(result["target_operations"]["delete"], 1)
                self.assertEqual(result["target_operations"]["match"], 1)

    def test_substitution_and_complete_missing_target_are_unsure(self):
        for hypothesis in ("ABCXEFGH", "ABCFGH"):
            with self.subTest(hypothesis=hypothesis):
                result = self.align(hypothesis)
                self.assertEqual(result["status"], "unsure")
                self.assertEqual(result["reason"], "mixed_or_missing_target")

    def test_repeated_windows_and_ambiguous_local_paths_are_unsure(self):
        for hypothesis in ("ABCDEFGHABCDEFGH", "ABCEFGHABCEFGH",
                           "ABCDDEFGH", "ABCEDFGH"):
            with self.subTest(hypothesis=hypothesis):
                result = self.align(hypothesis)
                self.assertEqual(result["status"], "unsure")
                self.assertEqual(result["reason"], "ambiguous_alignment")

    def test_insertions_at_both_target_boundaries_and_inside_are_unsure(self):
        for hypothesis in ("ABCXDEFGH", "ABCDXEFGH", "ABCDEXFGH"):
            with self.subTest(hypothesis=hypothesis):
                result = self.align(hypothesis)
                self.assertEqual(result["status"], "unsure")
                self.assertEqual(result["target_operations"]["insert"], 1)

    def test_context_budget_is_enforced_without_changing_target(self):
        reference = list("ABCDEFGHIJKL")
        allowed = probe.align_window(reference, list("AXCDEFGHZJKL"), 5, 7)
        noisy = probe.align_window(reference, list("AXCYEFGHZJKL"), 5, 7)
        self.assertEqual(allowed["context_edits"], 2)
        self.assertEqual(allowed["status"], "no_target_difference")
        self.assertEqual(noisy["context_edits"], 3)
        self.assertEqual(noisy["status"], "unsure")
        self.assertEqual(noisy["reason"], "noisy_context")
        self.assertEqual(probe.align_window(reference, list("AXCDEFGHZJKL"),
                                           5, 7, context_budget=1)["status"], "unsure")

    def test_empty_missing_context_and_oversized_inputs_are_unsure(self):
        cases = [(list("ABCDEFGH"), [], 3, 5), ([], [], 0, 0),
                 (list("ABCDEFGH"), list("ABCDEFGH"), 0, 2),
                 (list("ABCDEFGH"), list("ABCDEFGH"), 6, 8),
                 (list("ABCDEFGH"), list("ABCDEFGH"), 3, 3),
                 (list("ABCDEFGH"), ["Z"] * 4097, 3, 5),
                 (["A"] * 129, ["A"] * 129, 3, 5)]
        for args in cases:
            with self.subTest(lengths=(len(args[0]), len(args[1])), target=args[2:]):
                self.assertEqual(probe.align_window(*args)["status"], "unsure")


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.pins = json.loads((probe.HERE / "muaalem-pins.json").read_text())
        self.protocol = {"alphabet": list("ABCDEFGHXYZ"), "context_budget": 2}
        package = ModuleType("quran_transcript.phonetics.sifa")
        package.chunck_phonemes = list
        self.package = package
        self.patch = mock.patch.dict(sys.modules, {package.__name__: package})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        reference = mock.patch.object(probe, "make_reference",
                                      return_value=(list("ABCDEFGH"), 3, 5, "a" * 64))
        reference.start()
        self.addCleanup(reference.stop)

    def report(self, *hypotheses):
        return {"pins": self.pins, "clips": [
            {"index": i, "raw_phonemes": text} for i, text in enumerate(hypotheses)]}

    def test_outputs_ordered_counts_and_provenance_without_hypotheses(self):
        report = probe.evaluate(self.report("ABCDEFGH", "ABCEFGH", "ABCXEFGH"),
                                self.protocol, 99, 88, 3)
        self.assertEqual([row["index"] for row in report["clips"]], [0, 1, 2])
        self.assertEqual([row["status"] for row in report["clips"]],
                         ["no_target_difference", "possible_omission", "unsure"])
        self.assertEqual(report["protocol_sha256"],
                         probe.sha256_file(probe.HERE / "omission-protocol.json"))
        expected_files = ("omission_probe.py", "muaalem.py", "batch.py", "benchmark.py",
                          "omission-protocol.json", "omission-requirements-linux-cpu.lock")
        self.assertEqual(report["implementation_sha256"],
                         {name: probe.sha256_file(probe.HERE / name) for name in expected_files})
        for secret in ("raw_phonemes", "ABCDEFGH", "ABCEFGH", "ABCXEFGH"):
            self.assertNotIn(secret, json.dumps(report))

    def test_changed_model_pins_rejected(self):
        report = self.report("ABCDEFGH")
        report["pins"] = {"changed": True}
        with self.assertRaises(ValueError):
            probe.evaluate(report, self.protocol, 99, 88, 3)

    def test_unsupported_or_unparsed_symbols_are_unsure(self):
        for hypothesis in ("ABCD?EFGH", "ABCDEFGH "):
            result = probe.evaluate(self.report(hypothesis), self.protocol, 99, 88, 3)
            self.assertEqual(result["clips"][0]["reason"], "unsupported_sound_symbols")
        with mock.patch.object(self.package, "chunck_phonemes",
                        return_value=list("ABCDEFGH")):
            result = probe.evaluate(self.report("ABCDEFGH?"), self.protocol, 99, 88, 3)
            self.assertEqual(result["clips"][0]["status"], "unsure")

    def test_empty_too_many_and_malformed_hypotheses_fail_without_result(self):
        for report in (self.report(), self.report(*(["ABCDEFGH"] * 11)),
                       self.report(None), self.report("A" * 16385)):
            with self.subTest(count=len(report["clips"])):
                with self.assertRaises(ValueError):
                    probe.evaluate(report, self.protocol, 99, 88, 3)


class BoundaryTests(unittest.TestCase):
    def test_reference_package_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "__init__.py"
            source.write_bytes(b"synthetic reference package")
            protocol = {"package_sha256": {"__init__.py": hashlib.sha256(source.read_bytes()).hexdigest()}}
            with mock.patch.object(probe.importlib.util, "find_spec",
                                   return_value=SimpleNamespace(origin=str(source))):
                self.assertEqual(probe.verified_package(protocol), root)
                source.write_bytes(b"changed reference package")
                with self.assertRaises(ValueError):
                    probe.verified_package(protocol)

    def test_private_output_exclusive_permissions_and_sanitized_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "input.json", Path(folder) / "output.json"
            source.write_text("{}")
            argv = ["probe", "--input", str(source), "--output", str(output),
                    "--sura", "99", "--aya", "88", "--word", "3"]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                with mock.patch.object(probe, "evaluate", return_value={"clips": []}) as evaluate:
                    self.assertEqual(probe.main(), 0)
                    original = output.read_bytes()
                    self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(probe.main(), 1)
                    evaluate.assert_called_once()
                    self.assertEqual(output.read_bytes(), original)
                output.unlink()
                with mock.patch.object(probe, "evaluate", side_effect=ValueError("PRIVATE_PAYLOAD")):
                    self.assertEqual(probe.main(), 1)
                self.assertFalse(output.exists())
            self.assertNotIn("PRIVATE_PAYLOAD", stdout.getvalue())
            self.assertNotIn(str(source), stdout.getvalue())

    def test_checkout_output_rejected_before_evaluation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text("{}")
            output = probe.HERE / "must-not-create-omission-output.json"
            argv = ["probe", "--input", str(source), "--output", str(output),
                    "--sura", "99", "--aya", "88", "--word", "3"]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(probe, "evaluate") as evaluate:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(probe.main(), 1)
                evaluate.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
