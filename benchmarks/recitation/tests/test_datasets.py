"""Frozen public-source selection and download integrity; no network or speech."""

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_datasets as datasets


class Response(io.BytesIO):
    headers = {"test": "synthetic"}


class PublicSourceTests(unittest.TestCase):
    def transient_errors(self):
        return [datasets.urllib.error.HTTPError("https://example.invalid", code, "synthetic", {}, None)
                for code in (429, 500, 502, 503, 504)] + [
                    datasets.urllib.error.URLError("synthetic connection failure"),
                    TimeoutError("synthetic timeout")]

    def test_transient_download_failure_retries_same_url_and_recovers(self):
        url = "https://example.invalid/frozen-source"
        for error in self.transient_errors():
            with self.subTest(error=str(error)), \
                    mock.patch.object(datasets.urllib.request, "urlopen",
                                      side_effect=[error, Response(b"valid")]) as request, \
                    mock.patch.object(datasets.time, "sleep") as sleep:
                self.assertEqual(datasets.fetch(url)[0], b"valid")
                self.assertEqual(request.call_args_list, [mock.call(url, timeout=60)] * 2)
                sleep.assert_called_once_with(1)

    def test_persistent_transient_failure_has_four_attempts_and_bounded_backoff(self):
        for error in self.transient_errors():
            with self.subTest(error=str(error)), \
                    mock.patch.object(datasets.urllib.request, "urlopen", side_effect=error) as request, \
                    mock.patch.object(datasets.time, "sleep") as sleep, \
                    self.assertRaises(type(error)):
                datasets.fetch("https://example.invalid")
            self.assertEqual(request.call_count, 4)
            self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2), mock.call(4)])

    def test_permanent_http_error_is_not_retried(self):
        for code in (400, 401, 403, 404):
            error = datasets.urllib.error.HTTPError("https://example.invalid", code, "synthetic", {}, None)
            with self.subTest(code=code), \
                    mock.patch.object(datasets.urllib.request, "urlopen", side_effect=error) as request, \
                    mock.patch.object(datasets.time, "sleep") as sleep, \
                    self.assertRaises(datasets.urllib.error.HTTPError):
                datasets.fetch("https://example.invalid")
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_download_is_bounded(self):
        with mock.patch.object(datasets.urllib.request, "urlopen", return_value=Response(b"1234")):
            self.assertEqual(datasets.fetch("https://example.invalid", limit=4)[0], b"1234")
        with mock.patch.object(datasets.urllib.request, "urlopen", return_value=Response(b"12345")) as request, \
                mock.patch.object(datasets.time, "sleep") as sleep, \
                self.assertRaises(ValueError):
            datasets.fetch("https://example.invalid", limit=4)
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def viewer_result(self, index=7):
        source = datasets.SOURCES["openslr132"]
        audio = f"https://datasets-server.huggingface.co/cached-assets/{source['repo']}/--/{source['revision']}/toy.audio"
        row = {"text": "SYNTHETIC_REFERENCE", "audio": [{"src": audio}]}
        return {"rows": [{"row_idx": index, "row": row}]}, {"x-revision": source["revision"]}

    def test_viewer_requires_exact_revision_and_row_number(self):
        for changed in ("revision", "row"):
            payload, headers = self.viewer_result()
            if changed == "revision":
                headers["x-revision"] = "c" * 40
            else:
                payload["rows"][0]["row_idx"] = 8
            with self.subTest(changed=changed), \
                    mock.patch.object(datasets, "fetch", return_value=(json.dumps(payload).encode(), headers)), \
                    self.assertRaises(ValueError):
                datasets.source_row("openslr132", 7)

    def test_viewer_rejects_audio_outside_pinned_source(self):
        for url in ("https://example.invalid/audio.wav", "https://datasets-server.huggingface.co.evil.invalid/audio.wav",
                    "file:///tmp/private.wav"):
            payload, headers = self.viewer_result()
            payload["rows"][0]["row"]["audio"][0]["src"] = url
            with self.subTest(url=url), \
                    mock.patch.object(datasets, "fetch", return_value=(json.dumps(payload).encode(), headers)), \
                    self.assertRaises(ValueError):
                datasets.source_row("openslr132", 7)

    def test_viewer_fetches_requested_row_without_substitution(self):
        payload, headers = self.viewer_result()
        with mock.patch.object(datasets, "fetch", return_value=(json.dumps(payload).encode(), headers)) as fetch:
            row, url = datasets.source_row("openslr132", 7)
        self.assertEqual(row["text"], "SYNTHETIC_REFERENCE")
        self.assertIn("offset=7&length=1", fetch.call_args.args[0])
        self.assertIn(datasets.SOURCES["openslr132"]["revision"], url)

    def test_error_dataset_metadata_and_audio_use_immutable_revision(self):
        payload = b'{"text":"SYNTHETIC_REFERENCE","file_name":"temp_audio_chunks/chunks_recording_abc-123/chunk7.wav"}\n'
        with mock.patch.object(datasets, "fetch", return_value=(payload, {})) as fetch:
            metadata = datasets.error_metadata()
        revision = datasets.SOURCES["recitation_errors"]["revision"]
        self.assertIn(f"/resolve/{revision}/metadata.jsonl", fetch.call_args.args[0])
        row, url = datasets.source_row("recitation_errors", 0, metadata)
        self.assertEqual(row["text"], "SYNTHETIC_REFERENCE")
        self.assertIn(f"/resolve/{revision}/temp_audio_chunks/", url)

    def test_error_dataset_rejects_unsafe_audio_paths(self):
        for path in ("../private.wav", "/private.wav", "https://example.invalid/audio.wav",
                     "temp_audio_chunks/chunks_recording_abc/../../private.wav"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                datasets.source_row("recitation_errors", 0, [{"file_name": path}])


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dataset-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.destination = self.root / "prepared"
        self.reference = "PRIVATE_REFERENCE_SENTINEL"
        self.audio = b"synthetic placeholder bytes"
        sample = {"row_index": 7, "group": "sample-group",
                  "audio_sha256": hashlib.sha256(self.audio).hexdigest(),
                  "reference_sha256": datasets.text_hash(self.reference)}
        self.lock = {"schema_version": 1, "sources": copy.deepcopy(datasets.SOURCES),
                     "samples": {key: [dict(sample)] for key in datasets.SOURCES},
                     "selection": {key: {"method": "synthetic fixture"} for key in datasets.SOURCES}}

    def prepare(self, audio=None, reference=None):
        row = {"text": self.reference if reference is None else reference}
        with mock.patch.object(datasets, "error_metadata", return_value=[]), \
                mock.patch.object(datasets, "source_row", return_value=(row, "https://example.invalid/audio")), \
                mock.patch.object(datasets, "fetch", return_value=(self.audio if audio is None else audio, {})), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            datasets.prepare(self.lock, self.destination)
        return stdout.getvalue()

    def test_preparation_retains_hashes_and_reference_only_in_external_manifest(self):
        logs = self.prepare()
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o700)
        for key in datasets.SOURCES:
            manifest = json.loads((self.destination / f"{key}.json").read_text())
            sample = manifest["samples"][0]
            self.assertEqual(sample["reference_text"], self.reference)
            self.assertEqual(sample["audio_sha256"], hashlib.sha256(self.audio).hexdigest())
            self.assertEqual(Path(sample["audio_path"]).read_bytes(), self.audio)
            self.assertEqual(manifest["dataset"]["revision"], datasets.SOURCES[key]["revision"])
            self.assertEqual(manifest["dataset"]["selection"], self.lock["selection"][key])
        self.assertNotIn(self.reference, logs)
        self.assertNotIn(str(self.destination), logs)

    def test_changed_audio_or_reference_aborts_without_manifest(self):
        for changed in ("audio", "reference"):
            self.destination = self.root / changed
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.prepare(**{changed: b"changed bytes" if changed == "audio" else "CHANGED_REFERENCE"})
            self.assertEqual(list(self.destination.glob("*.json")), [])
            self.assertEqual(list(self.destination.glob("*.audio")), [])

    def test_audio_integrity_failure_is_not_retried(self):
        with mock.patch.object(datasets, "error_metadata", return_value=[]), \
                mock.patch.object(datasets, "source_row", return_value=(
                    {"text": self.reference}, "https://example.invalid/audio")), \
                mock.patch.object(datasets.urllib.request, "urlopen", return_value=Response(b"changed audio")) as request, \
                mock.patch.object(datasets.time, "sleep") as sleep, \
                self.assertRaises(ValueError):
            datasets.prepare(self.lock, self.destination)
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_reference_integrity_failure_never_downloads_audio_or_retries(self):
        with mock.patch.object(datasets, "error_metadata", return_value=[]), \
                mock.patch.object(datasets, "source_row", return_value=(
                    {"text": "changed reference"}, "https://example.invalid/audio")), \
                mock.patch.object(datasets.urllib.request, "urlopen") as request, \
                mock.patch.object(datasets.time, "sleep") as sleep, \
                self.assertRaises(ValueError):
            datasets.prepare(self.lock, self.destination)
        request.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_floating_or_changed_source_lock_rejected_before_download(self):
        self.lock["sources"]["openslr132"]["revision"] = "main"
        with mock.patch.object(datasets, "fetch") as fetch, self.assertRaises(ValueError):
            datasets.prepare(self.lock, self.destination)
        fetch.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_existing_directory_and_checkout_rejected_before_network(self):
        self.destination.mkdir()
        for destination in (self.destination, datasets.HERE / "data"):
            with self.subTest(destination=destination), mock.patch.object(datasets, "fetch") as fetch, \
                    self.assertRaises(ValueError):
                datasets.prepare(self.lock, destination)
            fetch.assert_not_called()

    def test_cli_failure_does_not_print_source_reference_or_path(self):
        with mock.patch.object(datasets.Path, "read_text", return_value=json.dumps(self.lock)), \
                mock.patch.object(datasets, "prepare", side_effect=ValueError("PRIVATE_REFERENCE_SENTINEL /private/path")), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            result = datasets.main(["--destination", str(self.destination)])
        self.assertEqual(result, 1)
        self.assertNotIn("PRIVATE_REFERENCE_SENTINEL", stdout.getvalue())
        self.assertNotIn("/private/path", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
