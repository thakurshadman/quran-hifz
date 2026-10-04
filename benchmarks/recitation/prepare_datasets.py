#!/usr/bin/env python3
"""Download only the frozen public evaluation subset; keep audio and text outside git."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from benchmark import HERE, outside_checkout, sha256_file

SOURCES = {
    "openslr132": {"repo": "deepdml/Quran_Speech_Dataset",
                   "revision": "9e3ddb53c201369c997ae1f8e2e0232a0e275cd0"},
    "recitation_errors": {"repo": "sobolev210/quran-recitation-errors",
                          "revision": "d196cd3132c69cd361d28cf6a8b442ae4e0bf0b4"},
}


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fetch(url, limit=10_000_000):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                payload = response.read(limit + 1)
                if len(payload) > limit:
                    raise ValueError("Public asset exceeds size limit")
                return payload, response.headers
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def error_metadata():
    source = SOURCES["recitation_errors"]
    url = f"https://huggingface.co/datasets/{source['repo']}/resolve/{source['revision']}/metadata.jsonl"
    payload, _ = fetch(url)
    return [json.loads(line) for line in payload.decode().splitlines()]


def source_row(dataset, index, metadata=None):
    source = SOURCES[dataset]
    if dataset == "openslr132":
        query = urllib.parse.urlencode({"dataset": source["repo"], "config": "default",
                                       "split": "train", "offset": index, "length": 1})
        payload, headers = fetch("https://datasets-server.huggingface.co/rows?" + query)
        if headers.get("x-revision") != source["revision"]:
            raise ValueError("Viewer dataset revision changed; do not substitute another sample")
        record = json.loads(payload)["rows"][0]
        if record["row_idx"] != index:
            raise ValueError("Wrong viewer row")
        row = record["row"]
        audio_url = row["audio"][0]["src"]
        prefix = f"https://datasets-server.huggingface.co/cached-assets/{source['repo']}/--/{source['revision']}/"
        if not audio_url.startswith(prefix):
            raise ValueError("Unexpected audio origin or revision")
        return row, audio_url
    row = metadata[index]
    path = row["file_name"]
    if not re.fullmatch(r"temp_audio_chunks/chunks_recording_[a-f0-9-]+/chunk[0-9]+\.wav", path):
        raise ValueError("Unexpected source audio path")
    return row, f"https://huggingface.co/datasets/{source['repo']}/resolve/{source['revision']}/{path}"


def prepare(lock, destination):
    destination = outside_checkout(destination)
    if destination.exists():
        raise ValueError("Use a new directory for each preparation")
    if lock.get("schema_version") != 1 or lock.get("sources") != SOURCES:
        raise ValueError("Unsupported frozen subset")
    destination.mkdir(parents=True, mode=0o700)
    metadata = error_metadata()
    for dataset in SOURCES:
        samples = []
        for item in lock["samples"][dataset]:
            row, url = source_row(dataset, item["row_index"], metadata)
            reference = row["text"]
            if text_hash(reference) != item["reference_sha256"]:
                raise ValueError("Source reference changed")
            payload, _ = fetch(url)
            if hashlib.sha256(payload).hexdigest() != item["audio_sha256"]:
                raise ValueError("Source audio changed")
            sample_id = f"row_{item['row_index']}"
            audio = destination / f"{dataset}_{sample_id}.audio"
            with audio.open("xb") as output:
                output.write(payload)
            samples.append({"id": sample_id, "group": item["group"], "audio_path": str(audio),
                            "audio_sha256": item["audio_sha256"], "reference_text": reference})
        manifest = {"schema_version": 1,
                    "dataset": {"id": dataset, "revision": SOURCES[dataset]["revision"],
                                "selection": lock["selection"][dataset]}, "samples": samples}
        with (destination / f"{dataset}.json").open("x") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
        print(f"Prepared {dataset}: {len(samples)} clips", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    try:
        lock = json.loads((HERE / "public-datasets.json").read_text())
        prepare(lock, args.destination)
    except (ValueError, OSError, KeyError, TypeError, IndexError):
        print("Preparation failed; check source availability, frozen hashes and destination. No substitution made.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
