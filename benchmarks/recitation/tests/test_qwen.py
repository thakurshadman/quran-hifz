"""Offline Qwen adapter contracts; no model downloads or speech inference."""

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qwen
import qwen_worker as worker
from test_fastconformer import ComparisonFixture


class WorkerFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="qwen-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "qwen"
        self.directory.mkdir()
        configs = {
            "config.json": {"model_type": "qwen3_asr", "architectures": ["Qwen3ASRForConditionalGeneration"]},
            "preprocessor_config.json": {"sampling_rate": 16000, "feature_extractor_type": "WhisperFeatureExtractor"},
            "tokenizer_config.json": {"tokenizer_class": "Qwen2TokenizerFast"},
        }
        for name, config in configs.items():
            (self.directory / name).write_text(json.dumps(config))
        (self.directory / "model.safetensors").write_bytes(b"synthetic weights placeholder")
        self.pin = {"schema_version": 1, "models": {"qwen": {
            "repo": "Qwen/Qwen3-ASR-0.6B", "revision": "5eb144179a02acc5e5ba31e748d22b0cf3e303b0",
            "files": [{"path": path.name, "bytes": path.stat().st_size,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in self.directory.iterdir()]}}}


class QwenAssetTests(WorkerFixture):
    def test_pin_rejects_remote_code_missing_weights_duplicates_and_floating_revision(self):
        for change in ("revision", "missing-weights", "duplicate", "executable", "hash", "size"):
            pin = copy.deepcopy(self.pin)
            model = pin["models"]["qwen"]
            if change == "revision":
                model["revision"] = "main"
            elif change == "missing-weights":
                model["files"] = [item for item in model["files"] if item["path"] != "model.safetensors"]
            elif change == "duplicate":
                model["files"].append(dict(model["files"][0]))
            elif change == "executable":
                model["files"][0]["path"] = "modeling_custom.py"
            elif change == "hash":
                model["files"][0]["sha256"] = "not-a-hash"
            else:
                model["files"][0]["bytes"] = True
            with self.subTest(change=change), mock.patch.object(Path, "read_text", return_value=json.dumps(pin)), \
                    self.assertRaises(ValueError):
                qwen.load_pin()
        with mock.patch.object(Path, "read_text", return_value=json.dumps(self.pin)):
            self.assertEqual(qwen.load_pin(), self.pin)

    def test_configs_require_registered_interfaces_and_disallow_custom_imports(self):
        worker.validate_configs(self.directory)
        for filename, field, value in (
            ("config.json", "auto_map", {"AutoModel": "custom.Model"}),
            ("config.json", "architectures", ["UntrustedModel"]),
            ("preprocessor_config.json", "sampling_rate", 48000),
            ("preprocessor_config.json", "feature_extractor_type", "CustomFeatures"),
            ("tokenizer_config.json", "tokenizer_class", "CustomTokenizer"),
            ("tokenizer_config.json", "processor_class", "CustomProcessor"),
        ):
            path = self.directory / filename
            original = path.read_text()
            path.write_text(json.dumps({**json.loads(original), field: value}))
            try:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    worker.validate_configs(self.directory)
            finally:
                path.write_text(original)

    def test_changed_and_unpinned_assets_fail_before_heavy_model_imports(self):
        config = {"model": "qwen", "directory": str(self.directory), "samples": []}
        with mock.patch.object(worker, "load_pin", return_value=self.pin):
            extra = self.directory / "modeling_custom.py"
            extra.write_text("untrusted placeholder")
            with self.assertRaises(ValueError):
                worker.run(config)
            extra.unlink()
            (self.directory / "model.safetensors").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                worker.run(config)


class RawOutputTests(unittest.TestCase):
    def test_raw_text_preserves_repetition_whitespace_and_empty_output(self):
        for text in ("  word word word\n", "", "language Arabic<asr_text>raw text"):
            self.assertEqual(worker.transcription_text([text]), text)
        for output in (None, [], ["a", "b"], ("a",), "a", [None], [123]):
            with self.subTest(output=output), self.assertRaises(ValueError):
                worker.transcription_text(output)

    def test_raw_helper_receives_same_audio_empty_context_and_arabic(self):
        audio = object()
        model = mock.Mock()
        model._infer_asr_transformers.return_value = [" repeated repeated "]
        self.assertEqual(worker.infer_raw(model, audio), " repeated repeated ")
        model._infer_asr_transformers.assert_called_once_with(contexts=[""], wavs=[audio], languages=["Arabic"])
        model.transcribe.assert_not_called()

    def test_worker_failure_does_not_echo_configuration(self):
        result = subprocess.run([sys.executable, "-S", str(qwen.HERE / "qwen_worker.py")],
                                input='{"model":"PRIVATE_REFERENCE PRIVATE_PATH"}', capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "Local Qwen inference failed.\n")


class QwenLoadingTests(WorkerFixture):
    def test_local_safe_float32_loading_and_actual_thinker_greedy_settings(self):
        def generation():
            value = SimpleNamespace(do_sample=True, num_beams=7)
            value.to_json_string = lambda **kwargs: json.dumps({"do_sample": value.do_sample, "num_beams": value.num_beams})
            return value
        parameter = SimpleNamespace(dtype="torch.float32", numel=lambda: 5)
        neural = SimpleNamespace(training=True, generation_config=generation(),
                                 thinker=SimpleNamespace(generation_config=generation()),
                                 parameters=lambda: iter([parameter]))
        neural.eval = lambda: setattr(neural, "training", False)
        model = SimpleNamespace(model=neural, backend="transformers", forced_aligner=None,
                                processor=SimpleNamespace(feature_extractor=SimpleNamespace(sampling_rate=16000)),
                                _infer_asr_transformers=mock.Mock(return_value=["raw raw"]))
        api = mock.Mock()
        api.from_pretrained.return_value = model
        audio = mock.Mock(size=16000)
        numpy = mock.Mock(__version__="fixture")
        numpy.fromfile.return_value = audio
        numpy.isfinite.return_value.all.return_value = True
        torch = mock.Mock(__version__="fixture", float32="FLOAT32")
        torch.inference_mode.side_effect = contextlib.nullcontext
        torch.are_deterministic_algorithms_enabled.return_value = False
        modules = {"numpy": numpy, "torch": torch, "transformers": SimpleNamespace(__version__="fixture"),
                   "qwen_asr": SimpleNamespace(Qwen3ASRModel=api)}
        config = {"model": "qwen", "directory": str(self.directory),
                  "samples": [{"index": 0, "pcm": str(self.root / "synthetic.f32")}]}
        with mock.patch.object(worker, "load_pin", return_value=self.pin), \
                mock.patch.dict(sys.modules, modules), \
                mock.patch("importlib.metadata.version", return_value="0.0.6"):
            result = worker.run(config)
        api.from_pretrained.assert_called_once_with(str(self.directory), dtype="FLOAT32", device_map="cpu",
            attn_implementation="sdpa", local_files_only=True, trust_remote_code=False, use_safetensors=True,
            max_inference_batch_size=1, max_new_tokens=512)
        self.assertFalse(neural.training)
        for component in (neural, neural.thinker):
            self.assertFalse(component.generation_config.do_sample)
            self.assertEqual(component.generation_config.num_beams, 1)
        model._infer_asr_transformers.assert_called_once_with(contexts=[""], wavs=[audio], languages=["Arabic"])
        torch.set_num_threads.assert_called_once_with(2)
        torch.set_num_interop_threads.assert_called_once_with(1)
        audio.fill.assert_called_once_with(0)
        self.assertEqual(result["samples"][0]["text"], "raw raw")
        self.assertFalse(result["configuration"]["wrapper_repetition_cleanup"])


class QwenOrchestrationTests(ComparisonFixture):
    def setUp(self):
        super().setUp()
        (self.cache / "mohammed").rename(self.cache / "qwen")
        self.models["models"]["qwen"] = self.models["models"].pop("mohammed")
        self.args.models = ["tilawi", "qwen"]

    def test_same_decoded_input_and_private_context_free_scoring_for_both_adapters(self):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps(self.private))
        with mock.patch.object(qwen, "load_datasets", return_value=([{"id": "toy"}], self.samples)), \
                mock.patch.object(qwen, "decode_audio", side_effect=self.decode) as decode, \
                mock.patch.object(qwen, "environment_info", return_value={}), \
                mock.patch.object(qwen, "sha256_file", return_value="a" * 64), \
                mock.patch.object(qwen.subprocess, "run", return_value=response) as process, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            report = qwen.run_comparison(self.args, self.models, self.models)
        self.assertEqual(decode.call_count, 2)
        configs = [json.loads(call.kwargs["input"]) for call in process.call_args_list]
        self.assertEqual([config["model"] for config in configs], ["tilawi", "qwen"])
        self.assertEqual(configs[0]["samples"], configs[1]["samples"])
        self.assertTrue(all(set(sample) == {"index", "pcm"} for sample in configs[0]["samples"]))
        self.assertEqual(report["models"]["qwen"]["overall"]["text_difference_pct"], 10)
        self.assertEqual(report["models"]["qwen"]["overall"], report["models"]["tilawi"]["overall"])
        self.assertNotIn("PRIVATE_", json.dumps(report) + json.dumps(configs) + stdout.getvalue())
        self.assertTrue(all(not path.exists() for path in self.decoded))

    def test_missing_qwen_trial_aborts_without_partial_tilawi_report(self):
        output = self.root / "report.json"
        incomplete = {**self.private, "samples": self.private["samples"][:1]}
        outcomes = [subprocess.CompletedProcess([], 0, stdout=json.dumps(payload))
                    for payload in (self.private, incomplete)]
        with mock.patch.object(qwen, "load_datasets", return_value=([{"id": "toy"}], self.samples)), \
                mock.patch.object(qwen, "validate_manifest", return_value=self.models), \
                mock.patch.object(qwen, "load_pin", return_value=self.models), \
                mock.patch.object(qwen, "decode_audio", side_effect=self.decode), \
                mock.patch.object(qwen, "environment_info", return_value={}), \
                mock.patch.object(qwen, "sha256_file", return_value="a" * 64), \
                mock.patch.object(qwen.subprocess, "run", side_effect=outcomes), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = qwen.main(self.cli(output))
        self.assertEqual(result, 1)
        self.assertFalse(output.exists())
        self.assertTrue(self.decoded)
        self.assertTrue(all(not path.exists() for path in self.decoded))
        self.assertNotIn("PRIVATE_", stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
