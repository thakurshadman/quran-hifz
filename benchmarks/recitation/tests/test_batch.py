"""Offline batch contracts: scoring, frozen inputs, failures and private data."""

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import batch


class BatchFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="batch-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.audio = self.root / "PRIVATE_AUDIO_NAME.wav"
        self.audio.write_bytes(b"synthetic placeholder, decoder mocked")
        self.data = {
            "schema_version": 1,
            "dataset": {"id": "toy", "revision": "a" * 40,
                        "selection": {"private_note": "PRIVATE_SELECTION"}},
            "samples": [
                {"id": "clip-1", "group": "short", "audio_path": str(self.audio),
                 "audio_sha256": hashlib.sha256(self.audio.read_bytes()).hexdigest(),
                 "reference_text": "PRIVATE_REFERENCE", "speaker_id": "PRIVATE_SPEAKER"},
                {"id": "clip-2", "group": "long", "audio_path": str(self.audio),
                 "audio_sha256": hashlib.sha256(self.audio.read_bytes()).hexdigest(),
                 "reference_text": "one two three four five six seven eight nine"},
            ],
        }
        self.manifest = self.root / "PRIVATE_MANIFEST.json"
        self.write_manifest()
        self.cache = self.root / "cache"
        self.models = {"models": {}}
        for key in ("tilawi", "tiny"):
            asset = self.cache / key / "weights.bin"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"weights")
            self.models["models"][key] = {
                "repo": "toy/model", "revision": "b" * 40,
                "files": [{"path": "weights.bin", "bytes": 7,
                           "sha256": hashlib.sha256(b"weights").hexdigest()}],
            }
        self.args = argparse.Namespace(cache=str(self.cache), manifest=[str(self.manifest)],
                                       models=["tilawi", "tiny"],
                                       output=str(self.root / "report.json"))
        self.worker = {
            "samples": [{"index": 0, "text": "PRIVATE_HYPOTHESIS", "seconds": 1},
                        {"index": 1, "text": self.data["samples"][1]["reference_text"], "seconds": 3}],
            "load_seconds": 0.5, "runtime": {"test": "mock"},
            "decoding": {"mode": "mock"}, "timer_scope": "mock inference",
        }

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.data))

    def decode(self, audio, pcm):
        pcm.write_bytes(b"\0" * 4)
        return {"seconds": 2, "decode_seconds": 0.01}

    def invoke(self, payload=None, error=None):
        stdout = json.dumps(self.worker if payload is None else payload)
        response = subprocess.CompletedProcess([], 0, stdout=stdout)
        with mock.patch.object(batch, "decode_audio", side_effect=self.decode) as decode, \
                mock.patch.object(batch, "environment_info", return_value={"test": True}), \
                mock.patch.object(batch.subprocess, "run", return_value=response, side_effect=error) as process, \
                contextlib.redirect_stdout(io.StringIO()) as logs:
            report = batch.run_batch(self.args, self.models)
        return report, decode, process, logs.getvalue()


class AggregateTests(BatchFixture):
    def test_word_weighted_score_is_not_mean_clip_percentage(self):
        _, samples = batch.load_datasets([str(self.manifest)])
        rows = [batch.score_trial(sample, trial, {"seconds": 2})
                for sample, trial in zip(samples, self.worker["samples"])]
        self.assertEqual([row["text_difference_pct"] for row in rows], [100, 0])
        overall = batch.summarize(rows)
        self.assertEqual(overall["text_difference_pct"], 10)
        self.assertEqual(overall["reference_words"], 10)
        self.assertEqual(overall["substitutions"], 1)
        self.assertEqual(overall["exact_match_pct"], 50)
        self.assertEqual(overall["completed_samples"], 2)
        self.assertEqual(overall["failed_samples"], 0)
        self.assertEqual(overall["median_inference_seconds"], 2)
        self.assertEqual(overall["p95_inference_seconds_nearest_rank"], 3)
        self.assertEqual(overall["real_time_factor"], 1)

    def test_empty_hypothesis_counts_omissions_without_excluding_clip(self):
        _, samples = batch.load_datasets([str(self.manifest)])
        row = batch.score_trial(samples[1], {"text": "", "seconds": 0}, {"seconds": 2})
        self.assertEqual(row["deletions"], 9)
        self.assertEqual(row["text_difference_pct"], 100)
        self.assertEqual(batch.summarize([row])["completed_samples"], 1)

    def test_insertions_can_exceed_one_hundred_percent(self):
        _, samples = batch.load_datasets([str(self.manifest)])
        row = batch.score_trial(samples[0], {"text": "one two three", "seconds": 1}, {"seconds": 2})
        self.assertEqual(row["text_difference_pct"], 300)

    def test_empty_cohort_is_not_reported_as_perfect(self):
        with self.assertRaises(ValueError):
            batch.summarize([])

    def test_invalid_timing_or_hypothesis_rejected(self):
        _, samples = batch.load_datasets([str(self.manifest)])
        for seconds in (-1, True, float("nan"), float("inf"), "1"):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                batch.score_trial(samples[0], {"seconds": seconds, "text": "toy"}, {"seconds": 2})
        for text in (None, 3, "x" * 20001, "word " * 1001):
            with self.subTest(kind=type(text).__name__), self.assertRaises(ValueError):
                batch.score_trial(samples[0], {"seconds": 1, "text": text}, {"seconds": 2})


class DatasetInputTests(BatchFixture):
    def test_manifest_provenance_retained_but_reference_and_speaker_not_exported(self):
        datasets, samples = batch.load_datasets([str(self.manifest)])
        self.assertEqual(datasets[0]["manifest_sha256"], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertEqual(datasets[0]["selected_samples"], 2)
        self.assertEqual(len(samples), 2)
        self.assertNotIn("PRIVATE_SELECTION", json.dumps(datasets))
        self.assertNotIn("speaker_id", samples[0])

    def test_changed_audio_is_rejected_before_running_model(self):
        self.audio.write_bytes(b"changed")
        with mock.patch.object(batch.subprocess, "run") as process, self.assertRaises(ValueError):
            batch.run_batch(self.args, self.models)
        process.assert_not_called()

    def test_duplicate_datasets_and_sample_ids_rejected(self):
        with self.assertRaises(ValueError):
            batch.load_datasets([str(self.manifest), str(self.manifest)])
        self.data["samples"][1]["id"] = "clip-1"
        self.write_manifest()
        with self.assertRaises(ValueError):
            batch.load_datasets([str(self.manifest)])

    def test_empty_samples_and_empty_passages_rejected(self):
        for samples in ([], [{**self.data["samples"][0], "reference_text": "..."}]):
            self.data["samples"] = samples
            self.write_manifest()
            with self.subTest(samples=len(samples)), self.assertRaises(ValueError):
                batch.load_datasets([str(self.manifest)])

    def test_audio_must_be_absolute_and_outside_checkout(self):
        for audio_path in ("relative.wav", str(batch.HERE / "private.wav")):
            self.data["samples"][0]["audio_path"] = audio_path
            self.write_manifest()
            with self.subTest(path=audio_path), self.assertRaises(ValueError):
                batch.load_datasets([str(self.manifest)])

    def test_manifest_in_another_checkout_rejected(self):
        repo = self.root / "other-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        path = repo / "manifest.json"
        path.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):
            batch.load_datasets([str(path)])

    def test_wrong_model_checksum_aborts_before_decoding(self):
        (self.cache / "tilawi" / "weights.bin").write_bytes(b"changed")
        with mock.patch.object(batch, "decode_audio") as decode, self.assertRaises(ValueError):
            batch.run_batch(self.args, self.models)
        decode.assert_not_called()


class BatchOrchestrationTests(BatchFixture):
    def test_shared_decode_separate_cohorts_and_private_worker_config(self):
        report, decode, process, logs = self.invoke()
        self.assertEqual(decode.call_count, 2)
        self.assertEqual(process.call_count, 2)
        for model in report["models"].values():
            self.assertEqual(model["overall"]["text_difference_pct"], 10)
            self.assertEqual(model["datasets"]["toy"]["completed_samples"], 2)
            self.assertEqual({row["group"]: row["text_difference_pct"] for row in model["groups"]},
                             {"short": 100, "long": 0})
        for call in process.call_args_list:
            config = json.loads(call.kwargs["input"])
            self.assertEqual([sample["index"] for sample in config["samples"]], [0, 1])
            self.assertTrue(all(set(sample) == {"index", "pcm"} for sample in config["samples"]))
            self.assertEqual(call.kwargs["env"]["HF_HUB_OFFLINE"], "1")
            self.assertEqual(call.kwargs["env"]["TRANSFORMERS_OFFLINE"], "1")
            for sample in config["samples"]:
                self.assertFalse(Path(sample["pcm"]).exists())
        serialized = json.dumps(report) + logs
        for secret in ("PRIVATE_REFERENCE", "PRIVATE_HYPOTHESIS", "PRIVATE_SELECTION",
                       "PRIVATE_SPEAKER", "PRIVATE_AUDIO_NAME", "PRIVATE_MANIFEST", str(self.root)):
            self.assertNotIn(secret, serialized)

    def test_missing_repeated_or_reordered_outputs_abort(self):
        trials = self.worker["samples"]
        for altered in (trials[:1], trials[::-1], [trials[0], trials[0]],
                        [{**trials[0], "index": False}, trials[1]],
                        [{**trials[0], "index": "0"}, trials[1]]):
            payload = {**self.worker, "samples": altered}
            with self.subTest(indices=[row["index"] for row in altered]), self.assertRaises(ValueError):
                self.invoke(payload)

    def test_invalid_load_timings_abort(self):
        for seconds in (-1, True, float("nan"), float("inf"), "1"):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                self.invoke({**self.worker, "load_seconds": seconds})

    def test_worker_failure_leaves_no_partial_report_or_temporary_pcm(self):
        output = self.root / "report.json"
        captured_pcm = []
        def fail(command, **kwargs):
            captured_pcm.extend(Path(sample["pcm"]) for sample in json.loads(kwargs["input"])["samples"])
            raise subprocess.CalledProcessError(1, command, output="PRIVATE_HYPOTHESIS", stderr="PRIVATE_SPEAKER")
        with mock.patch.object(batch, "decode_audio", side_effect=self.decode), \
                mock.patch.object(batch, "environment_info", return_value={}), \
                mock.patch.object(batch, "validate_manifest", return_value=self.models), \
                mock.patch.object(batch.subprocess, "run", side_effect=fail), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = batch.main(self.cli(output))
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())
        self.assertTrue(captured_pcm)
        self.assertTrue(all(not path.exists() for path in captured_pcm))
        self.assertNotIn("PRIVATE_", stdout.getvalue() + stderr.getvalue())

    def cli(self, output):
        return ["--manifest", str(self.manifest), "--cache", str(self.cache),
                "--models", "tilawi", "--output", str(output)]

    def test_output_cannot_overwrite_or_be_in_cache_or_checkout(self):
        existing = self.root / "existing.json"
        existing.write_text("keep")
        for output in (existing, self.cache / "report.json", batch.HERE / "report.json"):
            with self.subTest(output=output), mock.patch.object(batch, "run_batch") as runner, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(batch.main(self.cli(output)), 1)
                runner.assert_not_called()
        self.assertEqual(existing.read_text(), "keep")

    def test_atomic_report_has_private_permissions_and_cannot_replace(self):
        output = self.root / "report.json"
        batch.save_report(output, {"safe": True})
        self.assertEqual(json.loads(output.read_text()), {"safe": True})
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            batch.save_report(output, {"safe": False})
        self.assertEqual(json.loads(output.read_text()), {"safe": True})
        self.assertEqual(list(self.root.glob(".batch-report-*")), [])

    def test_bad_report_data_leaves_no_report_or_temporary_file(self):
        output = self.root / "report.json"
        with self.assertRaises(ValueError):
            batch.save_report(output, {"invalid": float("nan")})
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".batch-report-*")), [])


if __name__ == "__main__":
    unittest.main()
