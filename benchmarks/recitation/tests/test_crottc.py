"""Offline CROTTC decoding, pinned-cache and private-output contracts."""

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
import crottc


class Fixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="crottc-unit-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.content = b"synthetic pinned bytes"
        self.asset = {"name": "model.ckpt", "bytes": len(self.content),
                      "sha256": hashlib.sha256(self.content).hexdigest(),
                      "url": "https://example.invalid/resolve/" + "a" * 40 + "/model.ckpt"}
        self.pins = {"files": [self.asset]}


class RawDecodingTests(Fixture):
    def test_ctc_preserves_blank_separated_repeated_sounds_and_final_token(self):
        vocab = {0: "<blank>", 1: "b", 2: "aː"}
        ids = crottc.decode_ctc_ids([0, 1, 1, 0, 1, 2, 2, 0, 2])
        self.assertEqual(ids, [1, 1, 2, 2])
        self.assertEqual(crottc.render(ids, vocab), "b b aː aː")
        self.assertEqual(crottc.render(crottc.decode_ctc_ids([0, 0]), vocab), "")

    def test_unmapped_head_id_remains_visible_each_time(self):
        ids = crottc.decode_ctc_ids([70, 70, 0, 70, 1])
        self.assertEqual(crottc.render(ids, {0: "<blank>", 1: "a"}),
                         "[UNMAPPED:70] [UNMAPPED:70] a")

    def test_tokenizer_is_plain_literal_text_with_symbols_preserved(self):
        tokenizer = self.root / "tokenizer.ckpt"
        tokenizer.write_text("'<blank>' => 0\n'aː' => 1\n\"t'\" => 2\n================\nignored metadata")
        self.assertEqual(crottc.vocabulary(tokenizer), {0: "<blank>", 1: "aː", 2: "t'"})

    def test_tokenizer_rejects_executable_labels_duplicate_ids_and_wrong_blank(self):
        tokenizer = self.root / "tokenizer.ckpt"
        marker = self.root / "must-not-exist"
        malicious = f"__import__('pathlib').Path({str(marker)!r}).touch() => 1"
        for payload in ("'<blank>' => 0\n" + malicious,
                        "'<blank>' => 0\n'a' => 1\n'b' => 1",
                        "'wrong' => 0\n'a' => 1", "'<blank>' => 0\n123 => 1"):
            tokenizer.write_text(payload)
            with self.subTest(payload=payload), self.assertRaises((ValueError, SyntaxError)):
                crottc.vocabulary(tokenizer)
        self.assertFalse(marker.exists())


class AssetTests(Fixture):
    def test_valid_cache_uses_no_network_and_corruption_fails_closed(self):
        target = self.cache / "model.ckpt"
        target.write_bytes(self.content)
        with mock.patch.object(crottc.urllib.request, "urlopen") as network:
            crottc.assets(self.cache, self.pins, download=True)
        network.assert_not_called()
        for changed in (b"x" * len(self.content), self.content + b"extra"):
            target.write_bytes(changed)
            with self.subTest(size=len(changed)), mock.patch.object(crottc.urllib.request, "urlopen") as network, \
                    self.assertRaises(ValueError):
                crottc.assets(self.cache, self.pins)
            network.assert_not_called()

    def test_asset_path_traversal_and_external_symlink_are_rejected(self):
        for name in ("../escape", "/absolute", "nested/asset"):
            with self.subTest(name=name), mock.patch.object(crottc.urllib.request, "urlopen") as network, \
                    self.assertRaises(ValueError):
                crottc.assets(self.cache, {"files": [{**self.asset, "name": name}]}, download=True)
            network.assert_not_called()
        real = self.root / "external"
        real.write_bytes(self.content)
        (self.cache / "model.ckpt").symlink_to(real)
        with self.assertRaises(ValueError):
            crottc.assets(self.cache, self.pins)

    def test_bad_download_never_installs_and_removes_temporary_file(self):
        for payload in (b"x" * len(self.content), b"short", self.content + b"extra"):
            with self.subTest(size=len(payload)), \
                    mock.patch.object(crottc.urllib.request, "urlopen", return_value=io.BytesIO(payload)), \
                    self.assertRaises(ValueError):
                crottc.assets(self.cache, self.pins, download=True)
            self.assertEqual(list(self.cache.iterdir()), [])

    def test_verified_download_uses_pinned_url_and_bytes(self):
        with mock.patch.object(crottc.urllib.request, "urlopen", return_value=io.BytesIO(self.content)) as network:
            crottc.assets(self.cache, self.pins, download=True)
        network.assert_called_once_with(self.asset["url"], timeout=120)
        self.assertEqual((self.cache / "model.ckpt").read_bytes(), self.content)
        self.assertEqual([path.name for path in self.cache.iterdir()], ["model.ckpt"])


class PrivacyTests(Fixture):
    def cli(self, output):
        return ["crottc.py", "run", "--cache", str(self.cache),
                "--audio", str(self.root / "PRIVATE_INPUT.wav"), "--output", str(output)]

    def test_result_is_exclusive_private_0600_and_not_echoed(self):
        output = self.root / "private.json"
        report = {"clips": [{"index": 0, "raw_phonemes": "PRIVATE_HYPOTHESIS"}]}
        with mock.patch.object(sys, "argv", self.cli(output)), mock.patch.object(crottc, "run", return_value=report), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(crottc.main(), 0)
        self.assertEqual(json.loads(output.read_text()), report)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("PRIVATE_", stdout.getvalue())
        with mock.patch.object(sys, "argv", self.cli(output)), mock.patch.object(crottc, "run") as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(crottc.main(), 1)
        run.assert_not_called()
        self.assertEqual(json.loads(output.read_text()), report)

    def test_output_cannot_enter_git_or_cache(self):
        for output in (crottc.HERE / "private.json", self.cache / "private.json"):
            with self.subTest(output=output), mock.patch.object(sys, "argv", self.cli(output)), \
                    mock.patch.object(crottc, "run") as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(crottc.main(), 1)
            run.assert_not_called()

    def test_private_exception_is_sanitized_and_no_partial_output_saved(self):
        output = self.root / "private.json"
        error = subprocess.CalledProcessError(1, ["PRIVATE_INPUT"], output="PRIVATE_HYPOTHESIS")
        with mock.patch.object(sys, "argv", self.cli(output)), mock.patch.object(crottc, "run", side_effect=error), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(crottc.main(), 1)
        self.assertFalse(output.exists())
        self.assertNotIn("PRIVATE_", stdout.getvalue())

    def test_second_decode_failure_cleans_first_pcm_in_input_order(self):
        paths = [self.root / "first.wav", self.root / "second.wav"]
        for path in paths:
            path.write_bytes(b"synthetic placeholder")
        decoded, temporary = [], []
        def decode(source, pcm):
            decoded.append(source)
            if len(decoded) == 2:
                raise ValueError("synthetic decode failure")
            pcm.write_bytes(bytes(4))
            temporary.append(pcm)
            return {"seconds": 1, "samples": 16000, "decode_seconds": 0.001}
        with mock.patch.object(crottc, "assets"), mock.patch.object(crottc, "environment_info", return_value={}), \
                mock.patch.object(crottc, "decode_audio", side_effect=decode), self.assertRaises(ValueError):
            crottc.run(argparse.Namespace(audio=[str(path) for path in paths]), self.cache, self.pins)
        self.assertEqual(decoded, paths)
        self.assertTrue(temporary)
        self.assertTrue(all(not path.exists() for path in temporary))


if __name__ == "__main__":
    unittest.main()
