#!/usr/bin/env python3
"""Compare pinned recognizers with dataset-supplied passages, offline and in batches."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile

from benchmark import (HERE, MODEL_KEYS, asset_path, decode_audio, environment_info,
                       outside_checkout, sha256_file, validate_manifest, verify_asset)
from scoring import NORMALIZATION_VERSION, edit_counts, normalize

SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,159}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_SAMPLES = 2000


def safe_id(value):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError("Invalid non-identifying dataset, sample or group ID")
    return value


def load_datasets(paths):
    """Validate local manifests without exporting reference text or speaker IDs."""
    datasets, samples, seen_datasets, seen_samples = [], [], set(), set()
    for argument in paths:
        path = outside_checkout(argument)
        if not path.is_file() or path.stat().st_size > 25_000_000:
            raise ValueError("Invalid dataset manifest")
        data = json.loads(path.read_text())
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported dataset manifest")
        dataset = data["dataset"]
        dataset_id = safe_id(dataset["id"])
        revision = dataset["revision"]
        if not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", revision):
            raise ValueError("Invalid dataset revision")
        if dataset_id in seen_datasets:
            raise ValueError("Duplicate dataset")
        seen_datasets.add(dataset_id)
        rows = data["samples"]
        if not isinstance(rows, list) or not rows or len(rows) + len(samples) > MAX_SAMPLES:
            raise ValueError("Use 1–2000 samples")
        datasets.append({"id": dataset_id, "revision": revision,
                         "manifest_sha256": sha256_file(path), "selected_samples": len(rows),
                         "selection_metadata_sha256": hashlib.sha256(json.dumps(
                             dataset.get("selection", {}), sort_keys=True).encode()).hexdigest()})
        for row in rows:
            sample_id, group = safe_id(row["id"]), safe_id(row["group"])
            if (dataset_id, sample_id) in seen_samples:
                raise ValueError("Duplicate sample ID")
            seen_samples.add((dataset_id, sample_id))
            audio_value = row["audio_path"]
            if not isinstance(audio_value, str) or not Path(audio_value).is_absolute():
                raise ValueError("Audio paths must be absolute")
            audio = outside_checkout(audio_value)
            digest = row["audio_sha256"]
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                raise ValueError("Invalid audio checksum")
            if not audio.is_file() or sha256_file(audio) != digest:
                raise ValueError("Missing or changed audio")
            reference = row["reference_text"]
            if not isinstance(reference, str) or len(reference) > 20000:
                raise ValueError("Invalid supplied passage")
            words = normalize(reference)
            if not 1 <= len(words) <= 500:
                raise ValueError("Empty or overlong supplied passage")
            samples.append({"dataset": dataset_id, "id": sample_id, "group": group,
                            "audio_path": audio, "audio_sha256": digest, "reference": words})
    if not samples:
        raise ValueError("No selected samples")
    return datasets, samples


def score_trial(sample, trial, audio):
    seconds, text = trial["seconds"], trial["text"]
    if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Invalid worker timing")
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError("Invalid worker hypothesis")
    hypothesis = normalize(text)
    if len(hypothesis) > 1000:
        raise ValueError("Overlong worker hypothesis")
    counts = edit_counts(sample["reference"], hypothesis)
    return {"dataset": sample["dataset"], "id": sample["id"], "group": sample["group"],
            "audio_sha256": sample["audio_sha256"], "reference_words": len(sample["reference"]),
            "hypothesis_words": len(hypothesis), **counts,
            "text_difference_pct": 100 * sum(counts.values()) / len(sample["reference"]),
            "exact_match": sum(counts.values()) == 0,
            "audio_seconds": audio["seconds"], "inference_seconds": seconds,
            "real_time_factor": seconds / audio["seconds"]}


def summarize(rows):
    """Word-weighted text differences; clip-weighted exact matches and timings."""
    if not rows:
        raise ValueError("Cannot summarize an empty cohort")
    counts = {key: sum(row[key] for row in rows) for key in
              ("substitutions", "deletions", "insertions", "reference_words", "hypothesis_words")}
    edits = sum(counts[key] for key in ("substitutions", "deletions", "insertions"))
    durations = sorted(row["inference_seconds"] for row in rows)
    return {"selected_samples": len(rows), "completed_samples": len(rows), "failed_samples": 0,
            **counts, "text_difference_pct": 100 * edits / counts["reference_words"],
            "exact_match_samples": sum(row["exact_match"] for row in rows),
            "exact_match_pct": 100 * sum(row["exact_match"] for row in rows) / len(rows),
            "audio_seconds": sum(row["audio_seconds"] for row in rows),
            "total_inference_seconds": sum(durations),
            "median_inference_seconds": statistics.median(durations),
            "p95_inference_seconds_nearest_rank": durations[math.ceil(0.95 * len(durations)) - 1],
            "real_time_factor": sum(durations) / sum(row["audio_seconds"] for row in rows)}


def run_batch(args, models):
    cache = outside_checkout(args.cache)
    datasets, samples = load_datasets(args.manifest)
    for key in args.models:
        for asset in models["models"][key]["files"]:
            if not verify_asset(asset_path(cache, key, asset), asset):
                raise ValueError("Missing or changed model assets")
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "datasets": datasets, "environment": environment_info(),
              "normalization": NORMALIZATION_VERSION,
              "settings": {"warmups": 0, "repeats_per_clip": 1, "clip_order": "manifest order",
                           "reference": "dataset-supplied intended passage; no basmala removal",
                           "hypothesis_basmala_removed": False, "failure_policy": "abort; no report",
                           "model_loads": "once per model; clips processed sequentially"},
              "manifest_sha256": sha256_file(HERE / "models.json"),
              "implementation_sha256": {name: sha256_file(HERE / name) for name in
                  ("batch.py", "batch_node_runner.mjs", "batch_whisper_runner.py", "benchmark.py", "scoring.py")},
              "limitations": ["References are intended passages, not independently verified spoken transcripts",
                              "Text differences are not recognizer WER or learner mistake detection",
                              "Exploratory fixed subsets, not representative held-out test cohorts",
                              "Model training overlap is unknown; no generalization claim",
                              "Native full-clip CPU timings, not browser/live feedback latency",
                              "Timing scopes differ by adapter; first clip has no warmup",
                              "Descriptive statistics only; no confidence intervals or M0 acceptance claim"],
              "models": {}}
    with tempfile.TemporaryDirectory(prefix="quran-batch-") as temporary:
        directory = outside_checkout(temporary)
        configurations, audio_info = [], []
        for index, sample in enumerate(samples):
            pcm = directory / f"{index}.f32"
            audio_info.append(decode_audio(sample["audio_path"], pcm))
            configurations.append({"index": index, "pcm": str(pcm)})
        report["audio"] = {"sample_rate": 16000, "channels": 1, "format": "float32 little-endian",
                           "total_seconds": sum(item["seconds"] for item in audio_info),
                           "total_decode_seconds": sum(item["decode_seconds"] for item in audio_info)}
        for key in args.models:
            print(f"Starting {key}: {len(samples)} clips", flush=True)
            config = {"model": key, "directory": str(cache / key), "samples": configurations}
            runner = (["node", str(HERE / "batch_node_runner.mjs")] if key in ("tilawi", "tiny")
                      else [sys.executable, str(HERE / "batch_whisper_runner.py")])
            env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false",
                       OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
            result = subprocess.run(runner, input=json.dumps(config), text=True, capture_output=True,
                                    env=env, check=True, timeout=300 + 180 * len(samples))
            private = json.loads(result.stdout)
            trials = private["samples"]
            if (len(trials) != len(samples) or
                    any(type(trial["index"]) is not int or trial["index"] != index
                        for index, trial in enumerate(trials))):
                raise ValueError("Worker returned missing, repeated or unordered clips")
            rows = [score_trial(sample, trial, audio) for sample, trial, audio in zip(samples, trials, audio_info)]
            load_seconds = private["load_seconds"]
            if (isinstance(load_seconds, bool) or not isinstance(load_seconds, (float, int))
                    or not math.isfinite(load_seconds) or load_seconds < 0):
                raise ValueError("Invalid worker model-load timing")
            report["models"][key] = {
                "provenance": models["models"][key], "runtime": private["runtime"],
                "decoding": private["decoding"], "timer_scope": private["timer_scope"],
                "load_seconds": load_seconds, "overall": summarize(rows),
                "datasets": {dataset["id"]: summarize([row for row in rows if row["dataset"] == dataset["id"]])
                             for dataset in datasets},
                "groups": [{"dataset": dataset_id, "group": group,
                            **summarize([row for row in rows if (row["dataset"], row["group"]) == (dataset_id, group)])}
                           for dataset_id, group in sorted({(row["dataset"], row["group"]) for row in rows})],
                "clips": rows}
            del private, result, trials
            print(f"Completed {key}: {len(samples)} clips", flush=True)
    return report


def save_report(output, report):
    """Publish one complete report atomically, without replacing an existing file."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, prefix=".batch-report-",
                                         delete=False) as destination:
            temporary = Path(destination.name)
            json.dump(report, destination, indent=2, allow_nan=False)
            destination.write("\n")
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--models", nargs="+", choices=MODEL_KEYS, default=list(MODEL_KEYS))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        args.models = list(dict.fromkeys(args.models))
        cache, output = outside_checkout(args.cache), outside_checkout(args.output)
        if output.exists() or output == cache or cache in output.parents:
            raise ValueError("Output must be new and outside the model cache")
        models = validate_manifest(json.loads((HERE / "models.json").read_text()))
        report = run_batch(args, models)
        save_report(output, report)
        print("Saved report without audio, references, transcripts or speaker IDs.")
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        print("Batch failed. Check manifest, frozen assets, audio limits and dependencies. No report saved.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
