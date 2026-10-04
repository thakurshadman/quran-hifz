#!/usr/bin/env python3
"""Prepare the frozen exploratory RetaSy subset outside git, for local inference."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import urllib.parse

from benchmark import HERE, decode_audio, outside_checkout
from prepare_datasets import fetch, text_hash
from scoring import normalize

SOURCE = {"repo": "RetaSy/quranic_audio_dataset",
          "revision": "b1fcc39cbc045f367bb07e39025a0e3aaeabf34f"}
GROUPS = {"correct": 10, "in_correct": 10}
# Source labels only, not a canonical text mapping or a content-review claim.
# Prayer calls, supplications and ambiguous mixed passages are out of scope.
QURAN_SOURCE_LABELS = frozenset({
    "Al-Humazah", "Al-Faatihah", "Al-Asr", "Al-Ikhlas", "Al-Kafiroon", "An-Nasr",
    "Al-Falaq", "Al-Kauthar", "An-Nas", "Al-Qadr", "Ayat al-Kursi", "Al-Maaoon",
    "Al-NABAA", "Al-Fil", "Al-Masad", "Quraish",
})


def source_row(index):
    if type(index) is not int or not 0 <= index < 6828:
        raise ValueError("Invalid frozen row index")
    query = urllib.parse.urlencode({"dataset": SOURCE["repo"], "config": "default",
                                   "split": "train", "offset": index, "length": 1})
    payload, headers = fetch("https://datasets-server.huggingface.co/rows?" + query)
    if headers.get("x-revision") != SOURCE["revision"]:
        raise ValueError("Dataset revision changed")
    records = json.loads(payload)["rows"]
    if len(records) != 1 or records[0]["row_idx"] != index or records[0].get("truncated_cells"):
        raise ValueError("Unexpected or incomplete source row")
    row = records[0]["row"]
    url = row["audio"][0]["src"]
    prefix = f"https://datasets-server.huggingface.co/cached-assets/{SOURCE['repo']}/--/{SOURCE['revision']}/"
    if not isinstance(url, str) or not url.startswith(prefix):
        raise ValueError("Unexpected audio source or revision")
    return row, url


def _validate_metadata(row, group):
    reference, speaker = row["Aya"], row["reciter_id"]
    if (group not in GROUPS or row["final_label"] != group or row["reciter_qiraah"] != "hafs"
            or not isinstance(reference, str) or len(reference) > 20000
            or not 1 <= len(normalize(reference)) <= 500
            or not isinstance(speaker, str) or not speaker.strip()
            or type(row["golden"]) is not bool
            or not isinstance(row["duration_ms"], (float, int))
            or not 1000 <= row["duration_ms"] <= 30000):
        raise ValueError("Source no longer matches frozen eligibility")
    return reference, speaker


def validate_row(row, group):
    reference, speaker = _validate_metadata(row, group)
    if row.get("Surah") not in QURAN_SOURCE_LABELS:
        raise ValueError("Non-Quran or ambiguous source passage category")
    return reference, speaker


def candidate_order(records, seed=20261004):
    """Initial selection order only; reruns use frozen row IDs, never substitutes."""
    groups = {group: [] for group in GROUPS}
    for record in records:
        try:
            row = record["row"]
            group = row["final_label"]
            _validate_metadata(row, group)
            if record.get("truncated_cells"):
                continue
            groups[group].append(record)
        except (ValueError, KeyError, TypeError):
            continue
    generator = random.Random(seed)
    for group, candidates in groups.items():
        generator.shuffle(candidates)
        groups[group] = [record for record in candidates
                         if record["row"].get("Surah") in QURAN_SOURCE_LABELS]
    return groups


def existing_audio_hashes():
    lock = json.loads((HERE / "public-datasets.json").read_text())
    return {item["audio_sha256"] for items in lock["samples"].values() for item in items}


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def prepare(lock, destination):
    destination = outside_checkout(destination)
    if destination.exists():
        raise ValueError("Use a new destination")
    if (lock.get("schema_version") != 1 or lock.get("source") != SOURCE
            or not isinstance(lock.get("samples"), list)
            or len(lock["samples"]) != 20
            or Counter(item["group"] for item in lock["samples"]) != GROUPS
            or len({item["row_index"] for item in lock["samples"]}) != 20):
        raise ValueError("Unsupported frozen subset")
    destination.mkdir(parents=True, mode=0o700)
    samples, speakers, hashes = [], set(), existing_audio_hashes()
    golden, surahs = Counter(), Counter()
    with tempfile.TemporaryDirectory(prefix="retasy-decode-") as temporary:
        temporary = outside_checkout(temporary)
        for item in lock["samples"]:
            row, url = source_row(item["row_index"])
            reference, speaker = validate_row(row, item["group"])
            if speaker in speakers or text_hash(reference) != item["reference_sha256"]:
                raise ValueError("Repeated speaker or changed reference")
            payload, _ = fetch(url)
            digest = hashlib.sha256(payload).hexdigest()
            if digest in hashes or digest != item["audio_sha256"]:
                raise ValueError("Repeated or changed audio")
            sample_id = f"row_{item['row_index']}"
            audio = destination / f"retasy_{sample_id}.audio"
            descriptor = os.open(audio, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
            pcm = temporary / f"{sample_id}.f32"
            duration = decode_audio(audio, pcm)["seconds"]
            pcm.unlink()
            if not 1 <= duration <= 30:
                raise ValueError("Decoded audio outside duration bounds")
            speakers.add(speaker)
            hashes.add(digest)
            golden[str(row["golden"]).lower()] += 1
            surahs[row["Surah"]] += 1
            samples.append({"id": sample_id, "group": item["group"], "audio_path": str(audio),
                            "audio_sha256": digest, "reference_text": reference})
    if (dict(golden) != lock["selection"]["golden_counts"]
            or len(speakers) != lock["selection"]["distinct_nonempty_reciter_ids"]
            or dict(surahs) != lock["selection"]["selected_source_surah_counts"]
            or sorted(QURAN_SOURCE_LABELS) != lock["selection"]["allowed_source_surah_labels"]):
        raise ValueError("Source label metadata changed")
    manifest = {"schema_version": 1, "dataset": {"id": "retasy", "revision": SOURCE["revision"],
                "selection": lock["selection"]}, "samples": samples}
    write_private(destination / "retasy.json", manifest)
    print("Prepared RetaSy: 20 clips, 10 per label, 20 distinct source reciter IDs.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    try:
        lock = json.loads((HERE / "retasy-samples.json").read_text())
        prepare(lock, args.destination)
    except (ValueError, OSError, KeyError, TypeError, IndexError, subprocess.SubprocessError):
        print("RetaSy preparation failed. Check source availability, frozen hashes and destination; no substitution made.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
