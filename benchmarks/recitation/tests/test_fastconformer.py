"""Independent offline contracts for the native FastConformer comparison."""

import argparse
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fastconformer as comparison
import fastconformer_worker as worker


class TemporaryFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fastconformer-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)


class AssetAndArchiveTests(TemporaryFixture):
    def test_native_single_hypothesis_text_is_preserved_without_coercion(self):
        class Hypothesis:
            def __init__(self, text):
                self.text = text
        for text in ("PRIVATE_RECOGNIZED_TEXT", ""):
            self.assertEqual(worker.transcription_text([Hypothesis(text)], Hypothesis), text)

    def test_native_hypothesis_rejects_wrong_type_batch_shape_or_nonstring_text(self):
        class Hypothesis:
            def __init__(self, text):
                self.text = text
        class Impostor:
            text = "PRIVATE_RECOGNIZED_TEXT"
        valid = Hypothesis("fixture")
        for result in (None, [], [valid, valid], (valid,), "fixture", ["fixture"],
                       [object()], [Impostor()], [Hypothesis(None)], [Hypothesis(123)]):
            with self.subTest(kind=type(result).__name__), self.assertRaises(ValueError):
                worker.transcription_text(result, Hypothesis)

    def test_model_pin_requires_fixed_identity_revision_hash_size_and_path(self):
        original = comparison.load_pin()
        changes = [("repo", "untrusted/other"), ("revision", "main"),
                   ("path", "../weights.nemo"), ("sha256", "bad"),
                   ("bytes", 0), ("bytes", True)]
        for key, value in changes:
            pin = copy.deepcopy(original)
            target = pin["models"]["mohammed"]
            if key in ("path", "sha256", "bytes"):
                target = target["files"][0]
            target[key] = value
            with self.subTest(key=key, value=value), \
                    mock.patch.object(Path, "read_text", return_value=json.dumps(pin)), \
                    self.assertRaises(ValueError):
                comparison.load_pin()

    def make_archive(self, extra=None, omit=None):
        archive = self.root / "model.tar"
        with tarfile.open(archive, "w") as output:
            for name in sorted(worker.ARCHIVE_FILES - {omit}):
                content = b"synthetic fixture"
                member = tarfile.TarInfo(name)
                member.size = len(content)
                output.addfile(member, io.BytesIO(content))
            if extra is not None:
                output.addfile(extra, io.BytesIO(b"x" * extra.size) if extra.isfile() else None)
        return archive

    def test_only_complete_known_model_archive_is_accepted(self):
        destination = self.root / "extracted"
        destination.mkdir()
        worker.extract_archive(self.make_archive(), destination)
        self.assertEqual({p.name for p in destination.iterdir()}, worker.ARCHIVE_FILES)
        missing_destination = self.root / "incomplete"
        missing_destination.mkdir()
        with self.assertRaises(ValueError):
            worker.extract_archive(self.make_archive(omit="model_weights.ckpt"), missing_destination)

    def test_traversal_unknown_duplicate_links_and_special_files_rejected_before_extract(self):
        cases = []
        for name in ("../escape", "/absolute", "nested/../../escape", "bad\\path", "extra.py", "model_config.yaml"):
            member = tarfile.TarInfo(name)
            member.size = 1
            cases.append(member)
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE):
            member = tarfile.TarInfo("link-or-device")
            member.type = kind
            member.linkname = "../escape"
            cases.append(member)
        for index, member in enumerate(cases):
            destination = self.root / f"extracted-{index}"
            destination.mkdir()
            with self.subTest(name=member.name, kind=member.type), self.assertRaises(ValueError):
                worker.extract_archive(self.make_archive(extra=member), destination)
            self.assertEqual(list(destination.iterdir()), [])
        self.assertFalse((self.root / "escape").exists())

    def test_oversized_archive_is_rejected_without_allocating_or_extracting(self):
        member = tarfile.TarInfo("model_weights.ckpt")
        member.size = 1_000_000_001
        source = mock.MagicMock()
        source.__enter__.return_value = source
        source.getmembers.return_value = [member]
        with mock.patch.object(worker.tarfile, "open", return_value=source), self.assertRaises(ValueError):
            worker.extract_archive(self.root / "model.tar", self.root / "extracted")
        source.extractall.assert_not_called()

    def test_checkpoint_configuration_rejects_external_targets_and_resolvers(self):
        allowed = next(iter(worker.ALLOWED_TARGETS))
        worker.check_targets({"encoder": {"_target_": allowed}, "ordinary": ["literal", 1, None]})
        for config in ({"encoder": {"_target_": "os.system"}},
                       {"nested": [{"target": "untrusted.Module"}]},
                       {"cls": 123}, {"path": "${oc.env:PRIVATE_SECRET}"}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                worker.check_targets(config)
        nested = "leaf"
        for _ in range(32):
            nested = [nested]
        with self.assertRaises(ValueError):
            worker.check_targets(nested)

    def test_worker_forces_weights_only_offline_and_cpu_even_with_opposing_environment(self):
        program = ("import sys,os;sys.path.insert(0,sys.argv[1]);import fastconformer_worker;"
                   "print(os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'],os.environ['HF_HUB_OFFLINE'],"
                   "os.environ['TRANSFORMERS_OFFLINE'],repr(os.environ['CUDA_VISIBLE_DEVICES']))")
        env = dict(worker.os.environ, TORCH_FORCE_WEIGHTS_ONLY_LOAD="0", HF_HUB_OFFLINE="0",
                   TRANSFORMERS_OFFLINE="0", CUDA_VISIBLE_DEVICES="0")
        result = subprocess.run([sys.executable, "-S", "-c", program, str(comparison.HERE)],
                                env=env, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "1 1 1 ''")

    def test_missing_dependencies_produce_only_sanitized_worker_error(self):
        result = subprocess.run([sys.executable, "-S", str(comparison.HERE / "fastconformer_worker.py")],
                                input='{"secret":"PRIVATE_AUDIO_PATH PRIVATE_HYPOTHESIS"}',
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "Local FastConformer inference failed.\n")


class ComparisonFixture(TemporaryFixture):
    def setUp(self):
        super().setUp()
        self.samples = [
            {"dataset": "toy", "id": "clip-1", "group": "short", "audio_path": self.root / "PRIVATE_AUDIO_1",
             "audio_sha256": "a" * 64, "reference": ["PRIVATE_REFERENCE"]},
            {"dataset": "toy", "id": "clip-2", "group": "long", "audio_path": self.root / "PRIVATE_AUDIO_2",
             "audio_sha256": "b" * 64, "reference": "one two three four five six seven eight nine".split()},
        ]
        self.audio = [{"seconds": 2, "decode_seconds": 0.01}] * 2
        self.private = {"samples": [{"index": 0, "text": "PRIVATE_HYPOTHESIS", "seconds": 1},
                                    {"index": 1, "text": "one two three four five six seven eight nine", "seconds": 3}],
                        "load_seconds": 0.5, "runtime": {"fixture": True}, "decoding": "fixture",
                        "timer_scope": "fixture"}
        self.cache = self.root / "cache"
        self.models = {"models": {}}
        for key in ("tilawi", "mohammed"):
            path = self.cache / key / "weights.bin"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"weights")
            self.models["models"][key] = {"repo": "toy/model", "revision": "a" * 40,
                "files": [{"path": "weights.bin", "bytes": 7, "sha256": hashlib.sha256(b"weights").hexdigest()}]}
        self.args = argparse.Namespace(models=["tilawi", "mohammed"], cache=str(self.cache), manifest=["fixture"])
        self.decoded = []

    def decode(self, audio, pcm):
        self.decoded.append(pcm)
        pcm.write_bytes(b"\0" * 4)
        return {"seconds": 2, "decode_seconds": 0.01}

    def cli(self, output):
        return ["run", "--manifest", str(self.root / "manifest.json"), "--cache", str(self.cache), "--output", str(output)]


class SharedScoringTests(ComparisonFixture):
    def test_shared_word_weighting_and_cohort_totals_exclude_private_text(self):
        report = comparison.model_summary({}, self.private, self.samples, self.audio)
        self.assertEqual(report["overall"]["reference_words"], 10)
        self.assertEqual(report["overall"]["text_difference_pct"], 10)
        self.assertEqual(report["overall"]["exact_match_samples"], 1)
        self.assertEqual(report["datasets"]["toy"], report["overall"])
        self.assertEqual({row["group"]: row["text_difference_pct"] for row in report["groups"]},
                         {"short": 100, "long": 0})
        self.assertNotIn("PRIVATE_", json.dumps(report))

    def test_empty_speech_remains_in_denominator(self):
        private = copy.deepcopy(self.private)
        private["samples"][1]["text"] = ""
        report = comparison.model_summary({}, private, self.samples, self.audio)
        self.assertEqual(report["overall"]["completed_samples"], 2)
        self.assertEqual(report["overall"]["deletions"], 9)
        self.assertEqual(report["overall"]["reference_words"], 10)

    def test_missing_repeated_reordered_or_noninteger_worker_indices_fail(self):
        trials = self.private["samples"]
        for altered in (trials[:1], trials[::-1], [trials[0], trials[0]],
                        [{**trials[0], "index": False}, trials[1]],
                        [{**trials[0], "index": "0"}, trials[1]]):
            with self.subTest(indices=[row["index"] for row in altered]), self.assertRaises(ValueError):
                comparison.model_summary({}, {**self.private, "samples": altered}, self.samples, self.audio)

    def test_invalid_worker_timing_is_not_scored(self):
        for seconds in (-1, True, float("nan"), float("inf"), "1"):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                comparison.model_summary({}, {**self.private, "load_seconds": seconds}, self.samples, self.audio)


class ComparisonOrchestrationTests(ComparisonFixture):
    def test_both_models_receive_identical_decoded_audio_without_expected_text(self):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps(self.private))
        with mock.patch.object(comparison, "load_datasets", return_value=([{"id": "toy"}], self.samples)), \
                mock.patch.object(comparison, "decode_audio", side_effect=self.decode) as decoder, \
                mock.patch.object(comparison, "environment_info", return_value={}), \
                mock.patch.object(comparison.subprocess, "run", return_value=response) as process, \
                contextlib.redirect_stdout(io.StringIO()) as logs:
            report = comparison.run_comparison(self.args, self.models, self.models)
        self.assertEqual(decoder.call_count, 2)
        configs = [json.loads(call.kwargs["input"]) for call in process.call_args_list]
        self.assertEqual([config["model"] for config in configs], ["tilawi", "mohammed"])
        self.assertEqual(configs[0]["samples"], configs[1]["samples"])
        self.assertTrue(all(set(sample) == {"index", "pcm"} for sample in configs[0]["samples"]))
        for call in process.call_args_list:
            self.assertEqual(call.kwargs["env"]["TORCH_FORCE_WEIGHTS_ONLY_LOAD"], "1")
            self.assertEqual(call.kwargs["env"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(report["models"]["tilawi"]["overall"], report["models"]["mohammed"]["overall"])
        self.assertTrue(all(not path.exists() for path in self.decoded))
        self.assertNotIn("PRIVATE_", json.dumps(report) + json.dumps(configs) + logs.getvalue())

    def test_bad_asset_fails_before_any_decoding_or_inference(self):
        (self.cache / "mohammed" / "weights.bin").write_bytes(b"changed")
        with mock.patch.object(comparison, "load_datasets", return_value=([], self.samples)), \
                mock.patch.object(comparison, "decode_audio") as decode, \
                mock.patch.object(comparison.subprocess, "run") as process, self.assertRaises(ValueError):
            comparison.run_comparison(self.args, self.models, self.models)
        decode.assert_not_called()
        process.assert_not_called()

    def test_second_model_failure_saves_no_partial_report_and_removes_audio(self):
        output = self.root / "report.json"
        outcomes = [subprocess.CompletedProcess([], 0, stdout=json.dumps(self.private)),
                    subprocess.CalledProcessError(1, ["PRIVATE_COMMAND"], output="PRIVATE_HYPOTHESIS", stderr="PRIVATE_AUDIO")]
        with mock.patch.object(comparison, "load_datasets", return_value=([{"id": "toy"}], self.samples)), \
                mock.patch.object(comparison, "validate_manifest", return_value=self.models), \
                mock.patch.object(comparison, "load_pin", return_value=self.models), \
                mock.patch.object(comparison, "decode_audio", side_effect=self.decode), \
                mock.patch.object(comparison, "environment_info", return_value={}), \
                mock.patch.object(comparison.subprocess, "run", side_effect=outcomes), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = comparison.main(self.cli(output))
        self.assertEqual(result, 1)
        self.assertFalse(output.exists())
        self.assertTrue(self.decoded)
        self.assertTrue(all(not path.exists() for path in self.decoded))
        self.assertNotIn("PRIVATE_", stdout.getvalue() + stderr.getvalue())

    def test_output_cannot_overwrite_or_enter_git_or_cache(self):
        existing = self.root / "existing.json"
        existing.write_text("keep")
        for output in (existing, self.cache / "result.json", comparison.HERE / "result.json"):
            with self.subTest(output=output), mock.patch.object(comparison, "run_comparison") as run, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(comparison.main(self.cli(output)), 1)
                run.assert_not_called()
        self.assertEqual(existing.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
