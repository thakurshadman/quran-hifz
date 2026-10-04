"""RetaSy preparation contracts using invented non-speech fixtures only."""

from collections import Counter
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
import prepare_retasy as retasy


def source_row(index=0):
    return {"Aya": f"PRIVATE_REFERENCE_{index}", "reciter_id": f"PRIVATE_SPEAKER_{index}",
            "final_label": "correct" if index < 10 else "in_correct", "reciter_qiraah": "hafs",
            "golden": index < 10, "duration_ms": 2000, "Surah": "Al-Faatihah"}


class RetaSySourceTests(unittest.TestCase):
    def test_prayer_calls_supplications_and_ambiguous_categories_rejected(self):
        for category in ("Adhan", "Tashahhud", "Dua", "Other", "Mixed", "", None):
            with self.subTest(category=category), self.assertRaises(ValueError):
                retasy.validate_row({**source_row(), "Surah": category}, "correct")
        row = source_row()
        del row["Surah"]
        with self.assertRaises(ValueError):
            retasy.validate_row(row, "correct")

    def test_declared_quran_categories_allowed(self):
        self.assertEqual(len(retasy.QURAN_SOURCE_LABELS), 16)
        self.assertIn("Al-Faatihah", retasy.QURAN_SOURCE_LABELS)
        self.assertIn("Ayat al-Kursi", retasy.QURAN_SOURCE_LABELS)
        for category in retasy.QURAN_SOURCE_LABELS:
            with self.subTest(category=category):
                self.assertEqual(retasy.validate_row({**source_row(), "Surah": category}, "correct"),
                                 ("PRIVATE_REFERENCE_0", "PRIVATE_SPEAKER_0"))

    def test_category_filter_preserves_seeded_candidate_order_after_shuffle(self):
        records = [{"row_idx": index, "row": source_row(index)} for index in range(20)]
        original_order = retasy.candidate_order(records)
        excluded = {1, 4, 12, 18}
        for record in records:
            if record["row_idx"] in excluded:
                record["row"]["Surah"] = "Adhan"
        actual = retasy.candidate_order(records)
        for group in ("correct", "in_correct"):
            expected_ids = [record["row_idx"] for record in original_order[group]
                            if record["row_idx"] not in excluded]
            self.assertEqual([record["row_idx"] for record in actual[group]], expected_ids)

    def test_candidate_order_is_repeatable_seeded_and_preserves_input(self):
        records = [{"row_idx": index, "row": source_row(index)} for index in range(20)]
        unchanged = copy.deepcopy(records)
        first = retasy.candidate_order(records)
        self.assertEqual(first, retasy.candidate_order(records))
        self.assertNotEqual(first, retasy.candidate_order(records, seed=17))
        self.assertEqual(records, unchanged)
        for group, candidates in first.items():
            self.assertEqual(len(candidates), 10)
            self.assertTrue(all(record["row"]["final_label"] == group for record in candidates))
        self.assertEqual({record["row_idx"] for candidates in first.values() for record in candidates},
                         set(range(20)))

    def test_candidate_order_excludes_ineligible_and_truncated_records(self):
        records = [{"row_idx": 0, "row": source_row()}]
        for index, changed in enumerate(({"reciter_qiraah": "other"}, {"reciter_id": ""},
                                         {"final_label": "unknown"}, {"duration_ms": 500}), start=1):
            records.append({"row_idx": index, "row": {**source_row(index), **changed}})
        records += [{"row_idx": 5, "row": source_row(5), "truncated_cells": ["Aya"]},
                    {"row_idx": 6, "row": {}}]
        groups = retasy.candidate_order(records)
        self.assertEqual([record["row_idx"] for record in groups["correct"]], [0])
        self.assertEqual(groups["in_correct"], [])

    def viewer(self):
        prefix = f"https://datasets-server.huggingface.co/cached-assets/{retasy.SOURCE['repo']}/--/{retasy.SOURCE['revision']}/"
        row = {**source_row(), "audio": [{"src": prefix + "toy.audio"}]}
        return {"rows": [{"row_idx": 0, "row": row, "truncated_cells": []}]}, {
            "x-revision": retasy.SOURCE["revision"]}

    def test_exact_source_revision_row_and_audio_origin_required(self):
        for change in ("revision", "row", "truncated", "extra-row", "origin"):
            payload, headers = self.viewer()
            if change == "revision":
                headers["x-revision"] = "main"
            elif change == "row":
                payload["rows"][0]["row_idx"] = 1
            elif change == "truncated":
                payload["rows"][0]["truncated_cells"] = ["Aya"]
            elif change == "extra-row":
                payload["rows"] *= 2
            else:
                payload["rows"][0]["row"]["audio"][0]["src"] = "https://example.invalid/audio"
            with self.subTest(change=change), \
                    mock.patch.object(retasy, "fetch", return_value=(json.dumps(payload).encode(), headers)), \
                    self.assertRaises(ValueError):
                retasy.source_row(0)

    def test_valid_row_retains_unchanged_reference(self):
        payload, headers = self.viewer()
        with mock.patch.object(retasy, "fetch", return_value=(json.dumps(payload).encode(), headers)) as fetch:
            row, url = retasy.source_row(0)
        self.assertEqual(retasy.validate_row(row, "correct"), ("PRIVATE_REFERENCE_0", "PRIVATE_SPEAKER_0"))
        self.assertIn("offset=0&length=1", fetch.call_args.args[0])
        self.assertIn(retasy.SOURCE["revision"], url)

    def test_invalid_row_index_rejected_without_network(self):
        for index in (-1, 6828, True, 0.0, "0"):
            with self.subTest(index=index), mock.patch.object(retasy, "fetch") as fetch, \
                    self.assertRaises(ValueError):
                retasy.source_row(index)
            fetch.assert_not_called()

    def test_eligibility_rejects_other_labels_conventions_and_missing_ids(self):
        for field, value in (("final_label", "unknown"), ("reciter_qiraah", "other"),
                             ("reciter_id", " "), ("reciter_id", None), ("golden", "true"),
                             ("Aya", "..."), ("duration_ms", 999), ("duration_ms", 30001),
                             ("duration_ms", float("nan")), ("duration_ms", float("inf"))):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                retasy.validate_row({**source_row(), field: value}, "correct")
        for duration in (1000, 30000):
            self.assertEqual(retasy.validate_row({**source_row(), "duration_ms": duration}, "correct"),
                             ("PRIVATE_REFERENCE_0", "PRIVATE_SPEAKER_0"))


class RetaSyPreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="retasy-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.destination = self.root / "prepared"
        self.rows = [source_row(index) for index in range(20)]
        self.payloads = [f"synthetic audio placeholder {index}".encode() for index in range(20)]
        self.lock = {"schema_version": 1, "source": copy.deepcopy(retasy.SOURCE),
                     "selection": {"golden_counts": {"true": 10, "false": 10},
                                   "distinct_nonempty_reciter_ids": 20,
                                   "selected_source_surah_counts": {"Al-Faatihah": 20},
                                   "allowed_source_surah_labels": sorted(retasy.QURAN_SOURCE_LABELS)},
                     "samples": [{"row_index": index, "group": row["final_label"],
                                  "reference_sha256": retasy.text_hash(row["Aya"]),
                                  "audio_sha256": hashlib.sha256(self.payloads[index]).hexdigest()}
                                 for index, row in enumerate(self.rows)]}
        self.pcm_paths = []

    def decode(self, audio, pcm):
        self.pcm_paths.append(pcm)
        pcm.write_bytes(b"\0" * 4)
        return {"seconds": 2}

    def run_prepare(self, known_hashes=None, decoder=None):
        with mock.patch.object(retasy, "source_row", side_effect=lambda index: (
                    self.rows[index], f"https://example.invalid/{index}")) as rows, \
                mock.patch.object(retasy, "fetch", side_effect=lambda url: (
                    self.payloads[int(url.rsplit("/", 1)[1])], {})) as fetch, \
                mock.patch.object(retasy, "decode_audio", side_effect=decoder or self.decode), \
                mock.patch.object(retasy, "existing_audio_hashes", return_value=set(known_hashes or [])), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            retasy.prepare(self.lock, self.destination)
        return stdout.getvalue(), rows, fetch

    def test_preparation_is_balanced_private_and_has_no_speaker_ids(self):
        stdout, rows, fetch = self.run_prepare()
        self.assertEqual(rows.call_count, 20)
        self.assertEqual(fetch.call_count, 20)
        manifest_path = self.destination / "retasy.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(Counter(row["group"] for row in manifest["samples"]), {"correct": 10, "in_correct": 10})
        self.assertEqual(manifest["dataset"]["revision"], retasy.SOURCE["revision"])
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o700)
        self.assertEqual(manifest_path.stat().st_mode & 0o777, 0o600)
        for index, row in enumerate(manifest["samples"]):
            self.assertEqual(row["reference_text"], self.rows[index]["Aya"])
            audio = Path(row["audio_path"])
            self.assertEqual(audio.read_bytes(), self.payloads[index])
            self.assertEqual(audio.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("PRIVATE_SPEAKER", manifest_path.read_text())
        self.assertNotIn("PRIVATE_REFERENCE", stdout)
        self.assertNotIn(str(self.destination), stdout)
        self.assertTrue(self.pcm_paths)
        self.assertTrue(all(not path.exists() for path in self.pcm_paths))

    def test_repeated_speaker_rejected_without_manifest(self):
        self.rows[1]["reciter_id"] = self.rows[0]["reciter_id"]
        with self.assertRaises(ValueError):
            self.run_prepare()
        self.assertFalse((self.destination / "retasy.json").exists())
        self.assertTrue(all(not path.exists() for path in self.pcm_paths))

    def test_repeated_audio_within_subset_and_other_datasets_rejected(self):
        self.payloads[1] = self.payloads[0]
        self.lock["samples"][1]["audio_sha256"] = self.lock["samples"][0]["audio_sha256"]
        with self.assertRaises(ValueError):
            self.run_prepare()
        self.assertFalse((self.destination / "retasy.json").exists())
        self.destination = self.root / "known-audio"
        with self.assertRaises(ValueError):
            self.run_prepare(known_hashes={self.lock["samples"][0]["audio_sha256"]})
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_changed_audio_reference_or_label_aborts_without_manifest(self):
        for field in ("audio", "reference", "label"):
            self.destination = self.root / field
            if field == "audio":
                self.payloads[0] = b"changed"
            else:
                self.payloads[0] = b"synthetic audio placeholder 0"
                self.rows[0] = source_row()
                self.rows[0]["Aya" if field == "reference" else "final_label"] = "changed"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_prepare()
            self.assertFalse((self.destination / "retasy.json").exists())

    def test_actual_decoded_duration_checked_and_pcm_removed(self):
        for duration in (0.99, 30.01):
            self.destination = self.root / str(duration)
            def decode(audio, pcm):
                self.decode(audio, pcm)
                return {"seconds": duration}
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                self.run_prepare(decoder=decode)
            self.assertFalse((self.destination / "retasy.json").exists())
            self.assertTrue(all(not path.exists() for path in self.pcm_paths))

    def test_changed_golden_metadata_blocks_manifest(self):
        self.rows[0]["golden"] = False
        with self.assertRaises(ValueError):
            self.run_prepare()
        self.assertFalse((self.destination / "retasy.json").exists())

    def test_non_quran_category_aborts_before_audio_download(self):
        self.rows[0]["Surah"] = "Adhan"
        with mock.patch.object(retasy, "source_row", return_value=(self.rows[0], "https://example.invalid")), \
                mock.patch.object(retasy, "fetch") as fetch, \
                mock.patch.object(retasy, "existing_audio_hashes", return_value=set()), \
                self.assertRaises(ValueError):
            retasy.prepare(self.lock, self.destination)
        fetch.assert_not_called()
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_changed_source_category_counts_or_allowlist_block_manifest(self):
        self.rows[0]["Surah"] = "Al-Ikhlas"
        with self.assertRaises(ValueError):
            self.run_prepare()
        self.assertFalse((self.destination / "retasy.json").exists())
        self.rows[0]["Surah"] = "Al-Faatihah"
        self.destination = self.root / "changed-allowlist"
        self.lock["selection"]["allowed_source_surah_labels"].append("Adhan")
        with self.assertRaises(ValueError):
            self.run_prepare()
        self.assertFalse((self.destination / "retasy.json").exists())

    def test_frozen_lock_balance_and_unique_rows_required_before_network(self):
        original = copy.deepcopy(self.lock)
        for change in ("revision", "size", "balance", "duplicate"):
            self.lock = copy.deepcopy(original)
            if change == "revision":
                self.lock["source"]["revision"] = "main"
            elif change == "size":
                self.lock["samples"].pop()
            elif change == "balance":
                self.lock["samples"][0]["group"] = "in_correct"
            else:
                self.lock["samples"][1]["row_index"] = 0
            with self.subTest(change=change), mock.patch.object(retasy, "source_row") as source, \
                    self.assertRaises(ValueError):
                retasy.prepare(self.lock, self.destination)
            source.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_existing_destination_and_git_storage_rejected(self):
        self.destination.mkdir()
        for destination in (self.destination, retasy.HERE / "retasy-private"):
            with self.subTest(destination=destination), mock.patch.object(retasy, "source_row") as source, \
                    self.assertRaises(ValueError):
                retasy.prepare(self.lock, destination)
            source.assert_not_called()

    def test_private_write_refuses_overwrite(self):
        path = self.root / "private.json"
        retasy.write_private(path, {"keep": True})
        with self.assertRaises(FileExistsError):
            retasy.write_private(path, {"keep": False})
        self.assertEqual(json.loads(path.read_text()), {"keep": True})

    def test_cli_errors_do_not_print_private_payloads(self):
        with mock.patch.object(retasy.Path, "read_text", return_value=json.dumps(self.lock)), \
                mock.patch.object(retasy, "prepare", side_effect=ValueError("PRIVATE_REFERENCE PRIVATE_SPEAKER")), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            result = retasy.main(["--destination", str(self.destination)])
        self.assertEqual(result, 1)
        self.assertNotIn("PRIVATE_", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
