"""Offline exact-repetition checks; no invented spoken ground truth or inference."""

import argparse
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import repetition


class ClassificationAndPcmTests(unittest.TestCase):
    def test_categories_distinguish_two_copies_one_copy_and_changed_output(self):
        for original, repeated, expected in (
            ("a b", "a b a b", "exact_two_copy_hypothesis"),
            ("a b", "a b", "exact_single_copy"),
            ("a b", "a b a b extra", "other_different"),
            ("a b", "a b a", "other_different"),
            ("a b", "", "other_different"),
        ):
            with self.subTest(original=original, repeated=repeated):
                self.assertEqual(repetition.classify_pair(original, repeated)["category"], expected)

    def test_blank_baseline_is_unscorable_even_if_both_outputs_are_blank(self):
        for original, repeated in (("", ""), ("...", " "), ("", "words words")):
            with self.subTest(original=original, repeated=repeated):
                result = repetition.classify_pair(original, repeated)
                self.assertEqual(result["category"], "unscorable_blank_baseline")
                self.assertEqual(result["baseline_words"], 0)

    def test_normalization_preserves_repeated_words_in_the_baseline(self):
        exact = repetition.classify_pair("go, go!", "go go go go")
        collapsed = repetition.classify_pair("go, go!", "go go")
        self.assertEqual(exact, {"category": "exact_two_copy_hypothesis", "baseline_words": 2, "repeated_words": 4})
        self.assertEqual(collapsed["category"], "exact_single_copy")

    def test_audio_is_exact_original_4000_zero_frames_original(self):
        original = struct.pack("<4f", -0.25, 0.5, 0.125, -0.75)
        doubled = repetition.repeat_pcm(original)
        self.assertEqual(doubled[:len(original)], original)
        self.assertEqual(doubled[len(original):-len(original)], bytes(4000 * 4))
        self.assertEqual(doubled[-len(original):], original)
        self.assertEqual(len(doubled), 2 * len(original) + 16000)

    def test_pcm_bounds_reject_empty_partial_frame_oversize_or_changed_gap(self):
        for payload in (b"", b"abc", bytes(236001 * 4), "not bytes"):
            with self.subTest(size=len(payload)), self.assertRaises(ValueError):
                repetition.repeat_pcm(payload)
        for gap in (3999, 4001, True, 4000.0):
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                repetition.repeat_pcm(bytes(4), gap)
        self.assertEqual(len(repetition.repeat_pcm(bytes(236000 * 4))) // 4, 476000)


class RepetitionFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="repeat-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pcm = struct.pack("<4f", 0.1, -0.2, 0.3, -0.4)
        self.public = {"schema_version": 1, "sources": {"openslr132": {"repo": "toy/source", "revision": "a" * 40}},
                       "selection": {"openslr132": {"method": "fixture"}}, "samples": {"openslr132": []}}
        self.manifest_data = {"schema_version": 1,
            "dataset": {"id": "openslr132", "revision": "a" * 40, "selection": {"method": "fixture"}}, "samples": []}
        for index in range(50):
            audio = self.root / f"PRIVATE_AUDIO_{index}"
            audio.write_bytes(f"synthetic non-speech source {index}".encode())
            audio_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
            reference = "PRIVATE_REFERENCE"
            self.public["samples"]["openslr132"].append({"row_index": index, "group": "supplied_passage",
                "audio_sha256": audio_hash, "reference_sha256": repetition.digest(reference.encode())})
            self.manifest_data["samples"].append({"id": f"row_{index}", "group": "supplied_passage",
                "audio_path": str(audio), "audio_sha256": audio_hash, "reference_text": reference})
        self.manifest = self.root / "PRIVATE_MANIFEST.json"
        self.write_manifest()
        self.selection = {"schema_version": 1, "source": self.public["sources"]["openslr132"],
            "public_datasets_sha256": repetition.sha256_file(repetition.HERE / "public-datasets.json"),
            "selection": {"sample_rate": 16000, "gap_frames": 4000, "max_original_frames": 236000,
                          "selected_pairs": 10, "inferences": 20}, "samples": []}
        for index, frozen in enumerate(self.public["samples"]["openslr132"][:10]):
            self.selection["samples"].append({"id": f"row_{index}", "audio_sha256": frozen["audio_sha256"],
                "reference_sha256": frozen["reference_sha256"], "decoded_frames": 4,
                "pcm_sha256": repetition.digest(self.pcm),
                "repeated_pcm_sha256": repetition.digest(self.pcm + bytes(16000) + self.pcm)})
        asset = self.root / "cache" / "tilawi" / "weights.bin"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"weights")
        self.models = {"models": {"tilawi": {"repo": "toy/model", "revision": "b" * 40,
            "files": [{"path": "weights.bin", "bytes": 7, "sha256": repetition.digest(b"weights")}]}}}
        self.args = argparse.Namespace(cache=str(self.root / "cache"), manifest=str(self.manifest))
        self.worker = {"load_seconds": 0.25, "decoding": repetition.DECODING, "timer_scope": repetition.TIMER_SCOPE,
            "runtime": {"node": "v24.19.0", "onnxruntime_node": "1.30.0", "transformers_js": "4.3.0"}, "samples": []}
        for index in range(10):
            baseline = "PRIVATE_HYPOTHESIS" if index < 9 else ""
            repeated = baseline + " " + baseline if index < 7 else baseline if index == 7 else "PRIVATE_OTHER"
            self.worker["samples"].extend([{"index": index * 2, "text": baseline, "seconds": 0.01},
                                            {"index": index * 2 + 1, "text": repeated, "seconds": 0.02}])
        self.pcm_paths = []

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.manifest_data))

    def decode(self, audio, pcm):
        self.pcm_paths.append(pcm)
        pcm.write_bytes(self.pcm)
        return {"samples": 4, "seconds": 4 / 16000, "decode_seconds": 0.001}

    def run_probe(self, private=None):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps(self.worker if private is None else private))
        with mock.patch.object(repetition, "decode_audio", side_effect=self.decode), \
                mock.patch.object(repetition, "environment_info", return_value={}), \
                mock.patch.object(repetition.subprocess, "run", return_value=response) as process, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            report = repetition.run_repetition(self.args, self.models, self.selection, self.public)
        return report, process, stdout.getvalue()


class ManifestTests(RepetitionFixture):
    def test_complete_frozen_source_selects_only_pinned_pairs_in_order(self):
        dataset, selected = repetition.validate_inputs(self.manifest, self.selection, self.public)
        self.assertEqual(dataset["selected_samples"], 50)
        self.assertEqual([sample["id"] for sample in selected], [f"row_{index}" for index in range(10)])

    def test_source_reorder_reference_change_or_group_change_rejected(self):
        original = copy.deepcopy(self.manifest_data)
        for change in ("order", "reference", "group"):
            self.manifest_data = copy.deepcopy(original)
            if change == "order":
                self.manifest_data["samples"][:2] = self.manifest_data["samples"][:2][::-1]
            else:
                self.manifest_data["samples"][0]["reference_text" if change == "reference" else "group"] = "changed"
            self.write_manifest()
            with self.subTest(change=change), self.assertRaises(ValueError):
                repetition.validate_inputs(self.manifest, self.selection, self.public)

    def test_selection_reorder_duplicates_hash_change_and_changed_gap_rejected(self):
        original = copy.deepcopy(self.selection)
        for change in ("order", "duplicate", "audiohash", "pcmhash", "publichash", "gap"):
            selection = copy.deepcopy(original)
            if change == "order":
                selection["samples"][:2] = selection["samples"][:2][::-1]
            elif change == "duplicate":
                selection["samples"][1] = selection["samples"][0]
            elif change in ("audiohash", "pcmhash"):
                selection["samples"][0]["audio_sha256" if change == "audiohash" else "pcm_sha256"] = "changed"
            elif change == "publichash":
                selection["public_datasets_sha256"] = "c" * 64
            else:
                selection["selection"]["gap_frames"] = 3999
            with self.subTest(change=change), self.assertRaises(ValueError):
                repetition.validate_inputs(self.manifest, selection, self.public)


class OrchestrationTests(RepetitionFixture):
    def test_all_pairs_scored_without_private_text_and_blank_not_counted_as_success(self):
        report, process, stdout = self.run_probe()
        self.assertEqual(report["primary"], {"pairs": 10, "exact_two_copy_hypothesis": 7,
            "exact_single_copy": 1, "other_different": 1, "unscorable_blank_baseline": 1, "scorable_pairs": 9})
        self.assertEqual(report["auxiliary"]["original"]["completed_samples"], 10)
        self.assertEqual(report["auxiliary"]["repeated"]["reference_words"],
                         2 * report["auxiliary"]["original"]["reference_words"])
        self.assertEqual(report["audio"]["inferences"], 20)
        config = json.loads(process.call_args.kwargs["input"])
        self.assertEqual([sample["index"] for sample in config["samples"]], list(range(20)))
        self.assertTrue(all(set(sample) == {"index", "pcm"} for sample in config["samples"]))
        self.assertTrue(all(not Path(sample["pcm"]).exists() for sample in config["samples"]))
        self.assertNotIn("PRIVATE_", json.dumps(report) + json.dumps(config) + stdout)
        self.assertNotIn(str(self.root), json.dumps(report) + stdout)

    def test_wrong_pcm_hash_aborts_before_inference_and_removes_temporary_audio(self):
        for field in ("pcm_sha256", "repeated_pcm_sha256"):
            original = self.selection["samples"][0][field]
            self.selection["samples"][0][field] = "f" * 64
            with self.subTest(field=field), mock.patch.object(repetition, "decode_audio", side_effect=self.decode), \
                    mock.patch.object(repetition, "environment_info", return_value={}), \
                    mock.patch.object(repetition.subprocess, "run") as process, self.assertRaises(ValueError):
                repetition.run_repetition(self.args, self.models, self.selection, self.public)
            process.assert_not_called()
            self.assertTrue(all(not path.exists() for path in self.pcm_paths))
            self.selection["samples"][0][field] = original

    def test_worker_missing_reordered_repeated_or_boolean_indices_abort(self):
        trials = self.worker["samples"]
        for altered in (trials[:-1], trials[::-1], [trials[0]] * 20,
                        [{**trials[0], "index": False}] + trials[1:]):
            with self.subTest(length=len(altered)), self.assertRaises(ValueError):
                self.run_probe({**self.worker, "samples": altered})
        self.assertTrue(all(not path.exists() for path in self.pcm_paths))

    def test_worker_metadata_drops_unknown_fields_and_rejects_private_runtime(self):
        private = {**self.worker, "private_note": "PRIVATE_REFERENCE"}
        self.assertNotIn("PRIVATE_", json.dumps(repetition.worker_metadata(private)))
        private["runtime"] = {**private["runtime"], "path": "PRIVATE_PATH"}
        with self.assertRaises(ValueError):
            repetition.worker_metadata(private)
        for field, value in (("load_seconds", float("nan")), ("load_seconds", True),
                             ("decoding", "changed"), ("timer_scope", "changed")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                repetition.worker_metadata({**self.worker, field: value})

    def test_invalid_inference_timing_is_not_scored(self):
        private = copy.deepcopy(self.worker)
        private["samples"][0]["seconds"] = float("inf")
        with self.assertRaises(ValueError):
            self.run_probe(private)

    def test_failure_saves_no_report_or_private_exception(self):
        output = self.root / "result.json"
        error = subprocess.CalledProcessError(1, ["PRIVATE_PATH"], output="PRIVATE_HYPOTHESIS")
        with mock.patch.object(repetition, "run_repetition", side_effect=error), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = repetition.main(["--manifest", str(self.manifest), "--cache", self.args.cache,
                                      "--output", str(output)])
        self.assertEqual(status, 1)
        self.assertFalse(output.exists())
        self.assertNotIn("PRIVATE_", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
