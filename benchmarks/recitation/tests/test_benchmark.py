"""Offline integrity, input, privacy and orchestration checks; no speech fixtures."""

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmark
from test_scoring import source_records


def asset(name, content):
    return {"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def toy_manifest():
    models = {key: {"repo": "toy/model", "revision": "a" * 40,
                    "files": [asset("weights.bin", b"weights")]}
              for key in benchmark.MODEL_KEYS}
    models["tilawi"]["files"] += [asset("quran.json", json.dumps(source_records()).encode()),
                                  asset("TANZIL-NOTICE.txt", b"synthetic test notice")]
    return {"schema_version": 1, "models": models}


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="benchmark-unit-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)


class IntegrityTests(TemporaryTest):
    def test_hash_and_size_both_required(self):
        path = self.root / "model"
        data = b"known asset bytes"
        expected = asset("model", data)
        self.assertFalse(benchmark.verify_asset(path, expected))
        path.write_bytes(data)
        self.assertTrue(benchmark.verify_asset(path, expected))
        self.assertEqual(benchmark.sha256_file(path), hashlib.sha256(data).hexdigest())
        path.write_bytes(b"x" * len(data))
        self.assertFalse(benchmark.verify_asset(path, expected))
        path.write_bytes(data + b"extra")
        self.assertFalse(benchmark.verify_asset(path, expected))

    def test_asset_symlink_rejected(self):
        real = self.root / "real"
        real.write_bytes(b"data")
        link = self.root / "link"
        link.symlink_to(real)
        self.assertFalse(benchmark.verify_asset(link, asset("link", b"data")))

    def test_manifest_rejects_floating_revision_and_unsafe_paths(self):
        benchmark.validate_manifest(toy_manifest())
        for revision in ("main", "a" * 39, "A" * 40):
            manifest = toy_manifest()
            manifest["models"]["tiny"]["revision"] = revision
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                benchmark.validate_manifest(manifest)
        for path in ("../escape", "/absolute", "a/../../escape", "a\\escape", "a//b", "./a"):
            manifest = toy_manifest()
            manifest["models"]["tiny"]["files"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                benchmark.validate_manifest(manifest)

    def test_manifest_rejects_missing_provenance_and_duplicate_assets(self):
        manifest = toy_manifest()
        manifest["models"]["tilawi"]["files"].pop()
        with self.assertRaises(ValueError):
            benchmark.validate_manifest(manifest)
        manifest = toy_manifest()
        manifest["models"]["tiny"]["files"] *= 2
        with self.assertRaises(ValueError):
            benchmark.validate_manifest(manifest)

    def test_cache_parent_symlink_cannot_escape(self):
        cache = self.root / "cache"
        cache.mkdir()
        (cache / "tiny").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            benchmark.asset_path(cache, "tiny", asset("escape", b"x"))

    def test_corrupt_download_not_installed_and_temporary_removed(self):
        expected = asset("weights.bin", b"valid")
        manifest = {"models": {"tiny": {"repo": "toy/model", "revision": "a" * 40,
                                          "files": [expected]}}}
        for response in (b"wrong", b"oversized", b"v"):
            with self.subTest(response=response):
                cache = self.root / "cache"
                with mock.patch.object(benchmark.urllib.request, "urlopen", return_value=io.BytesIO(response)), self.assertRaises(ValueError):
                    benchmark.download_models(cache, ["tiny"], manifest)
                self.assertEqual(list(cache.rglob("*bin")), [])
                self.assertEqual(list(cache.rglob(".download-*")), [])

    def test_verified_cache_never_downloads(self):
        cache = self.root / "cache"
        target = cache / "tiny" / "weights.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"valid")
        manifest = {"models": {"tiny": {"files": [asset("weights.bin", b"valid")]}}}
        with mock.patch.object(benchmark.urllib.request, "urlopen") as network:
            benchmark.download_models(cache, ["tiny"], manifest)
        network.assert_not_called()

    def test_valid_download_uses_immutable_revision_and_repairs_stale_cache(self):
        cache = self.root / "cache"
        target = cache / "tiny" / "weights.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"stale")
        manifest = {"models": {"tiny": {"repo": "toy/model", "revision": "b" * 40,
                                          "files": [asset("weights.bin", b"valid")]}}}
        with mock.patch.object(benchmark.urllib.request, "urlopen", return_value=io.BytesIO(b"valid")) as network, contextlib.redirect_stdout(io.StringIO()):
            benchmark.download_models(cache, ["tiny"], manifest)
        self.assertEqual(network.call_args.args[0], "https://huggingface.co/toy/model/resolve/" + "b" * 40 + "/weights.bin")
        self.assertEqual(target.read_bytes(), b"valid")
        self.assertEqual(list(cache.rglob(".download-*")), [])


class PrivacyAndCliTests(TemporaryTest):
    def test_current_checkout_rejected_even_via_symlink(self):
        link = self.root / "repo-link"
        link.symlink_to(benchmark.CHECKOUT, target_is_directory=True)
        for path in (benchmark.CHECKOUT / "private.wav", link / "private.wav"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                benchmark.outside_checkout(path)

    def test_other_git_checkout_rejected(self):
        for kind in ("directory", "worktree-file"):
            repo = self.root / kind
            repo.mkdir()
            if kind == "directory":
                (repo / ".git").mkdir()
            else:
                (repo / ".git").write_text("gitdir: /unused")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                benchmark.outside_checkout(repo / "nested" / "private.json")

    def cli_args(self, output):
        return ["run", "--models", "tilawi", "--cache", str(self.root / "cache"),
                "--audio", str(self.root / "audio.wav"), "--output", str(output)]

    def test_no_overwriting_report_or_input(self):
        report = self.root / "existing.json"
        report.write_text("keep me")
        with mock.patch.object(benchmark, "run_models") as runner, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(benchmark.main(self.cli_args(report)), 1)
        runner.assert_not_called()
        self.assertEqual(report.read_text(), "keep me")

    def test_report_cannot_be_inside_cache(self):
        with mock.patch.object(benchmark, "run_models") as runner, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(benchmark.main(self.cli_args(self.root / "cache" / "result.json")), 1)
        runner.assert_not_called()

    def test_repeat_bounds_rejected_before_inference(self):
        for flag, value in (("--repeats", "0"), ("--repeats", "101"), ("--warmups", "-1"), ("--warmups", "21")):
            with self.subTest(flag=flag, value=value), mock.patch.object(benchmark, "run_models") as runner, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(benchmark.main(self.cli_args(self.root / "result.json") + [flag, value]), 1)
                runner.assert_not_called()

    def test_error_does_not_print_private_path_or_worker_payload(self):
        stderr = io.StringIO()
        error = subprocess.CalledProcessError(1, ["private-path"], output="secret hypothesis", stderr="private audio")
        with mock.patch.object(benchmark, "run_models", side_effect=error), contextlib.redirect_stderr(stderr):
            self.assertEqual(benchmark.main(self.cli_args(self.root / "result.json")), 1)
        for private in ("private-path", "secret hypothesis", "private audio", str(self.root)):
            self.assertNotIn(private, stderr.getvalue())
        self.assertFalse((self.root / "result.json").exists())

    def test_help_requires_no_model_dependencies(self):
        result = subprocess.run([sys.executable, "-S", str(benchmark.HERE / "benchmark.py"), "run", "--help"],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--basmala", result.stdout)

    def test_successful_report_is_private_and_does_not_print_content(self):
        output = self.root / "aggregate.json"
        stdout = io.StringIO()
        with mock.patch.object(benchmark, "run_models", return_value={"models": {}}), contextlib.redirect_stdout(stdout):
            self.assertEqual(benchmark.main(self.cli_args(output)), 0)
        self.assertEqual(json.loads(output.read_text()), {"models": {}})
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(output), stdout.getvalue())

    def test_python_worker_errors_are_sanitized_without_dependencies(self):
        result = subprocess.run([sys.executable, "-S", str(benchmark.HERE / "whisper_runner.py")],
                                input='{"private":"SECRET_SENTINEL"}', text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "Local inference failed.\n")

    @unittest.skipUnless(shutil.which("node"), "node unavailable")
    def test_node_worker_errors_do_not_echo_private_configuration(self):
        pcm = self.root / "private-name.f32"
        pcm.write_bytes(b"\0" * 4)
        result = subprocess.run(["node", str(benchmark.HERE / "node_runner.mjs")],
                                input=json.dumps({"model": "SECRET_SENTINEL", "pcm": str(pcm)}),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "Local inference failed.\n")


class AudioBoundsTests(TemporaryTest):
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg tools unavailable")
    def test_synthetic_silence_is_decoded_to_declared_format(self):
        path = self.root / "synthetic.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\0" * 8000 * 4)
        pcm = self.root / "decoded.f32"
        result = benchmark.decode_audio(path, pcm)
        self.assertEqual((result["sample_rate"], result["channels"], result["samples"]), (16000, 1, 16000))
        self.assertEqual(pcm.stat().st_size, 16000 * 4)
        self.assertEqual(result["seconds"], 1)

    def test_probe_invalid_or_long_duration_rejected_before_decode(self):
        for duration in ("0", "-1", "30.0001", "inf", "nan"):
            probe = subprocess.CompletedProcess([], 0, stdout=json.dumps({"format": {"duration": duration}}))
            with self.subTest(duration=duration), mock.patch.object(benchmark.subprocess, "run", return_value=probe) as process, self.assertRaises(ValueError):
                benchmark.decode_audio(self.root / "fake.wav", self.root / "fake.f32")
            self.assertEqual(process.call_count, 1)

    def test_decoded_size_checked_even_when_probe_understates_duration(self):
        for size in (0, 3, 480001 * 4):
            pcm = self.root / "fake.f32"
            def process(command, **kwargs):
                if command[0] == "ffprobe":
                    return subprocess.CompletedProcess(command, 0, stdout='{"format":{"duration":"1"}}')
                pcm.write_bytes(b"\0" * size)
                return subprocess.CompletedProcess(command, 0)
            with self.subTest(size=size), mock.patch.object(benchmark.subprocess, "run", side_effect=process), self.assertRaises(ValueError):
                benchmark.decode_audio(self.root / "fake.wav", pcm)


class OrchestrationTests(TemporaryTest):
    def setup_run(self):
        cache = self.root / "cache"
        manifest = toy_manifest()
        content = {"weights.bin": b"weights", "quran.json": json.dumps(source_records()).encode(),
                   "TANZIL-NOTICE.txt": b"synthetic test notice"}
        for key, _, entry in benchmark.needed_assets(manifest, ["tilawi"]):
            path = cache / key / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content[entry["path"]])
        audio = self.root / "input.wav"
        audio.write_bytes(b"synthetic input, decoding is mocked")
        args = argparse.Namespace(cache=str(cache), audio=str(audio), models=["tilawi"],
                                  warmups=1, repeats=2, basmala="exclude")
        return args, manifest

    def test_mocked_adapter_scores_intended_text_and_discards_hypothesis(self):
        args, manifest = self.setup_run()
        private = {"runs": [{"text": "PRIVATE_SENTINEL", "seconds": 0.2},
                             {"text": "PRIVATE_SENTINEL", "seconds": 0.4}],
                   "runtime": {"test_adapter": "1"}, "decoding": "synthetic fixture",
                   "timer_scope": "mock inference only", "load_seconds": 1.0}
        seen = []
        def worker(command, **kwargs):
            config = json.loads(kwargs["input"])
            seen.append(config)
            self.assertEqual(config["repeats"], 2)
            self.assertEqual(config["warmups"], 1)
            self.assertNotIn("reference", config)
            self.assertEqual(kwargs["env"]["HF_HUB_OFFLINE"], "1")
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(private))
        def decode(audio, pcm):
            pcm.write_bytes(b"\0" * 64)
            return {"seconds": 2.0, "samples": 32000, "sample_rate": 16000, "channels": 1}
        stdout = io.StringIO()
        with mock.patch.object(benchmark, "environment_info", return_value={"test": True}), mock.patch.object(benchmark, "decode_audio", side_effect=decode), mock.patch.object(benchmark.subprocess, "run", side_effect=worker), contextlib.redirect_stdout(stdout):
            report = benchmark.run_models(args, manifest)
        encoded = json.dumps(report)
        self.assertNotIn("PRIVATE_SENTINEL", encoded + stdout.getvalue())
        self.assertNotIn(str(self.root), encoded + stdout.getvalue())
        self.assertEqual(report["settings"]["reference_words"], 15)
        self.assertIn("not ASR WER", " ".join(report["limitations"]))
        model = report["models"]["tilawi"]
        self.assertAlmostEqual(model["median_inference_seconds"], 0.3)
        self.assertEqual(model["runs"][0]["substitutions"], 1)
        self.assertEqual(model["runs"][0]["deletions"], 14)
        self.assertEqual(model["runs"][0]["text_difference_pct"], 100)
        self.assertEqual(model["runs"][0]["real_time_factor"], 0.1)
        self.assertFalse(Path(seen[0]["pcm"]).exists(), "temporary audio must be cleaned up")

    def test_stale_cache_fails_before_any_audio_or_model_processing(self):
        args, manifest = self.setup_run()
        (Path(args.cache) / "tilawi" / "weights.bin").write_bytes(b"changed")
        with mock.patch.object(benchmark, "decode_audio") as decode, mock.patch.object(benchmark.subprocess, "run") as process, self.assertRaises(ValueError):
            benchmark.run_models(args, manifest)
        decode.assert_not_called()
        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
