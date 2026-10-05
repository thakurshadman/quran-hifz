"""Offline raw-phoneme and private-output contracts; no user recordings."""

import argparse
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
import muaalem


class CtcTests(unittest.TestCase):
    def test_adjacent_frames_collapse_but_blank_separated_repeats_remain(self):
        self.assertEqual(muaalem.decode_ctc_ids([0, 1, 1, 0, 1, 1, 2, 2, 0, 2]), [1, 1, 2, 2])
        self.assertEqual(muaalem.decode_ctc_ids([4, 4]), [4])
        self.assertEqual(muaalem.decode_ctc_ids([1, 0, 2]), [1, 2])

    def test_empty_and_blank_only_outputs_stay_empty(self):
        self.assertEqual(muaalem.decode_ctc_ids([]), [])
        self.assertEqual(muaalem.decode_ctc_ids([0, 0, 0]), [])
        self.assertEqual(muaalem.decode_ctc_ids([2, 2, 7, 2], blank=7), [2, 2])

    def test_invalid_frame_ids_and_blank_rejected(self):
        for token in (-1, True, 1.0, "1"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                muaalem.decode_ctc_ids([token])
        for blank in (-1, True, 0.0):
            with self.subTest(blank=blank), self.assertRaises(ValueError):
                muaalem.decode_ctc_ids([1], blank)

    def test_raw_symbols_vowels_repeats_and_spaces_are_not_normalized(self):
        vocab = {"[PAD]": 0, "b": 1, "َ": 2, "ː": 3, " ": 4}
        self.assertEqual(muaalem.phoneme_text([1, 2, 2, 3, 4, 1], vocab), "bََː b")
        self.assertEqual(muaalem.phoneme_text([], vocab), "")
        for ids in ([0], [99], [True]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                muaalem.phoneme_text(ids, vocab)
        for invalid in ({"[PAD]": 1, "b": 2}, {"[PAD]": 0, "b": 1, "c": 1}):
            with self.assertRaises(ValueError):
                muaalem.phoneme_text([], invalid)


class Fixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="muaalem-unit-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.cache = self.root / "cache"
        self.pins = json.loads((muaalem.HERE / "muaalem-pins.json").read_text())
        sources = {
            "configuration_multi_level_ctc.py": b"VALUE = 1\n",
            "modeling_multi_level_ctc.py": b"from .configuration_multi_level_ctc import VALUE\nWav2Vec2BertForMultilevelCTC = ('synthetic', VALUE)\n",
        }
        for kind in ("model", "source"):
            (self.cache / kind).mkdir(parents=True)
            for asset in self.pins[kind]["files"]:
                name = asset["path"] if kind == "model" else asset["local_name"]
                content = sources[name] if kind == "source" else b"synthetic asset"
                if name == "vocab.json":
                    content = json.dumps({"phonemes": {"[PAD]": 0, "b": 1, "َ": 2}}).encode()
                (self.cache / kind / name).write_bytes(content)
                asset["bytes"] = len(content)
                asset["sha256"] = hashlib.sha256(content).hexdigest()
        self.audio = []
        for index in range(2):
            path = self.root / f"PRIVATE_INPUT_{index}.wav"
            path.write_bytes(b"synthetic non-speech placeholder")
            self.audio.append(str(path))
        self.args = argparse.Namespace(cache=str(self.cache), audio=self.audio)
        self.pcm_paths = []

    def decode(self, source, pcm):
        self.pcm_paths.append(pcm)
        pcm.write_bytes(bytes(8))
        return {"samples": 2, "seconds": 2 / 16000, "decode_seconds": 0.001}

    def cli(self, output):
        return ["run", "--cache", str(self.cache), "--audio", self.audio[0], "--output", str(output)]


class PinAndSourceTests(Fixture):
    def test_required_model_and_reviewed_source_pins_are_strict(self):
        muaalem.validate_pins(self.pins)
        for change in ("revision", "repo", "missing", "duplicate", "source-path", "checksum"):
            pins = copy.deepcopy(self.pins)
            if change == "revision":
                pins["model"]["revision"] = "main"
            elif change == "repo":
                pins["model"]["repo"] = "other/model"
            elif change == "missing":
                pins["model"]["files"].pop()
            elif change == "duplicate":
                pins["model"]["files"][0] = pins["model"]["files"][1]
            elif change == "source-path":
                pins["source"]["files"][0]["path"] = "../other.py"
            else:
                pins["source"]["files"][0]["sha256"] = "invalid"
            with self.subTest(change=change), self.assertRaises(ValueError):
                muaalem.validate_pins(pins)

    def test_changed_cache_and_symlink_escape_rejected(self):
        muaalem.verify_cache(self.cache, self.pins)
        asset = self.pins["model"]["files"][0]
        target = self.cache / "model" / asset["path"]
        target.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            muaalem.verify_cache(self.cache, self.pins)
        target.unlink()
        target.symlink_to(self.root / "elsewhere")
        with self.assertRaises(ValueError):
            muaalem.cache_file(self.cache, "model", asset)

    def test_only_verified_source_executes_without_package_init_or_bytecode(self):
        (self.cache / "source/__init__.py").write_text("raise RuntimeError('UNREVIEWED_INIT')")
        (self.cache / "source/modeling_multi_level_ctc.pyc").write_bytes(b"unreviewed bytecode")
        with mock.patch.dict(sys.modules):
            self.assertEqual(muaalem.load_source(self.cache, self.pins), ("synthetic", 1))
        path = self.cache / "source/configuration_multi_level_ctc.py"
        path.write_text("raise RuntimeError('UNREVIEWED_SOURCE')")
        with mock.patch.dict(sys.modules), self.assertRaises(ValueError):
            muaalem.load_source(self.cache, self.pins)


class AudioAndPrivacyTests(Fixture):
    def test_private_sixty_second_limit_checks_probe_and_actual_frames(self):
        for duration in ("0", "-1", "60.001", "nan", "inf"):
            result = subprocess.CompletedProcess([], 0, stdout=json.dumps({"format": {"duration": duration}}))
            with self.subTest(duration=duration), mock.patch.object(muaalem.subprocess, "run", return_value=result) as process, \
                    self.assertRaises(ValueError):
                muaalem.decode_audio(Path(self.audio[0]), self.root / "pcm")
            self.assertEqual(process.call_count, 1)
        pcm = self.root / "pcm"
        def process(command, **kwargs):
            if command[0] == "ffprobe":
                return subprocess.CompletedProcess(command, 0, stdout='{"format":{"duration":"36.5"}}')
            pcm.write_bytes(bytes(584000 * 4))
            return subprocess.CompletedProcess(command, 0)
        with mock.patch.object(muaalem.subprocess, "run", side_effect=process) as runner:
            self.assertEqual(muaalem.decode_audio(Path(self.audio[0]), pcm)["seconds"], 36.5)
        for call in runner.call_args_list:
            self.assertIn("file,pipe", call.args[0])
        def understated(command, **kwargs):
            result = process(command, **kwargs)
            if command[0] == "ffmpeg":
                pcm.write_bytes(bytes(960001 * 4))
            return result
        with mock.patch.object(muaalem.subprocess, "run", side_effect=understated), self.assertRaises(ValueError):
            muaalem.decode_audio(Path(self.audio[0]), pcm)

    def test_private_report_is_exclusive_0600_and_not_echoed(self):
        output = self.root / "result.json"
        report = {"clips": [{"index": 0, "raw_phonemes": "PRIVATE_HYPOTHESIS"}]}
        with mock.patch.object(muaalem, "run", return_value=report), contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(muaalem.main(self.cli(output)), 0)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(output.read_text()), report)
        self.assertNotIn("PRIVATE_", stdout.getvalue())
        with mock.patch.object(muaalem, "run") as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(muaalem.main(self.cli(output)), 1)
        run.assert_not_called()
        self.assertEqual(json.loads(output.read_text()), report)

    def test_output_in_git_or_model_cache_rejected_before_processing(self):
        for output in (muaalem.HERE / "private.json", self.cache / "private.json"):
            with self.subTest(output=output), mock.patch.object(muaalem, "run") as run, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(muaalem.main(self.cli(output)), 1)
            run.assert_not_called()

    def test_failure_does_not_publish_partial_report_or_private_exception(self):
        output = self.root / "failed.json"
        with mock.patch.object(muaalem, "run", side_effect=RuntimeError("PRIVATE_INPUT PRIVATE_HYPOTHESIS")), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(muaalem.main(self.cli(output)), 1)
        self.assertFalse(output.exists())
        self.assertNotIn("PRIVATE_", stderr.getvalue())

    def test_decoding_failure_removes_already_decoded_audio(self):
        def fail_second(source, pcm):
            if self.pcm_paths:
                raise ValueError("synthetic failure")
            return self.decode(source, pcm)
        with mock.patch.object(muaalem, "decode_audio", side_effect=fail_second), self.assertRaises(ValueError):
            muaalem.run(self.args, self.pins)
        self.assertTrue(self.pcm_paths)
        self.assertTrue(all(not path.exists() for path in self.pcm_paths))

    def test_ordered_raw_phoneme_run_has_no_reference_paths_or_input_hashes(self):
        arrays = [mock.Mock(), mock.Mock()]
        numpy = mock.Mock(__version__="fixture")
        numpy.fromfile.side_effect = arrays
        torch = mock.Mock(__version__="fixture", float32="FLOAT32")
        torch.inference_mode.side_effect = contextlib.nullcontext
        torch.isfinite.return_value.all.return_value.item.return_value = True
        torch.are_deterministic_algorithms_enabled.return_value = False
        logits = mock.Mock(ndim=3, shape=(1, 6, 3))
        logits.argmax.return_value.__getitem__ = mock.Mock(return_value=SimpleNamespace(tolist=lambda: [1, 1, 0, 1, 2, 2]))
        model = mock.Mock(config=SimpleNamespace(pad_token_id=0, level_to_vocab_size={"phonemes": 3}))
        model.return_value = SimpleNamespace(logits={"phonemes": logits})
        model_class = mock.Mock()
        model_class.from_pretrained.return_value = (model, {})
        extractor = mock.Mock(sampling_rate=16000, return_value={"synthetic_features": True})
        extractor_class = mock.Mock()
        extractor_class.from_pretrained.return_value = extractor
        modules = {"numpy": numpy, "torch": torch,
            "transformers": SimpleNamespace(__version__="fixture", SeamlessM4TFeatureExtractor=extractor_class)}
        with mock.patch.dict(sys.modules, modules), mock.patch.object(muaalem, "load_source", return_value=model_class), \
                mock.patch.object(muaalem, "quiet_library_logs", side_effect=contextlib.nullcontext), \
                mock.patch.object(muaalem, "decode_audio", side_effect=self.decode):
            report = muaalem.run(self.args, self.pins)
        self.assertEqual([clip["index"] for clip in report["clips"]], [0, 1])
        self.assertEqual([clip["raw_phonemes"] for clip in report["clips"]], ["bbَ", "bbَ"])
        self.assertEqual([call.args[0] for call in extractor.call_args_list], arrays)
        self.assertTrue(all(call.kwargs["truncation"] is False for call in extractor.call_args_list))
        self.assertTrue(all(not path.exists() for path in self.pcm_paths))
        for array in arrays:
            array.fill.assert_called_once_with(0)
        self.assertNotIn("PRIVATE_", json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertTrue(all("audio_sha256" not in clip and "path" not in clip for clip in report["clips"]))
        self.assertEqual(model_class.from_pretrained.call_args.kwargs["use_safetensors"], True)
        self.assertEqual(model_class.from_pretrained.call_args.kwargs["local_files_only"], True)


if __name__ == "__main__":
    unittest.main()
