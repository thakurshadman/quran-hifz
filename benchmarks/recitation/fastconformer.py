#!/usr/bin/env python3
"""Compare two FastConformer adapters on shared local clips and scoring rules."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
import re
import subprocess
import sys
import tempfile

from batch import load_datasets, save_report, score_trial, summarize
from benchmark import (HERE, asset_path, decode_audio, download_models, environment_info,
                       outside_checkout, sha256_file, validate_manifest, verify_asset)
from scoring import NORMALIZATION_VERSION

MODEL_KEYS = ("tilawi", "mohammed")


def load_pin():
    pin = json.loads((HERE / "fastconformer_models.json").read_text())
    if pin.get("schema_version") != 1 or set(pin.get("models", {})) != {"mohammed"}:
        raise ValueError("Unsupported model pin")
    model = pin["models"]["mohammed"]
    if (model["repo"] != "mohammed/fastconformer-quran-ar"
            or not re.fullmatch(r"[0-9a-f]{40}", model["revision"])
            or len(model["files"]) != 1):
        raise ValueError("Invalid model identity")
    asset = model["files"][0]
    if (asset["path"] != "phase3_full/phase3_full_wer0.0014.nemo"
            or type(asset["bytes"]) is not int or asset["bytes"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])):
        raise ValueError("Invalid model integrity metadata")
    return pin


def model_summary(model, private, samples, audio_info):
    trials = private["samples"]
    if (len(trials) != len(samples) or any(type(trial["index"]) is not int or trial["index"] != index
                                         for index, trial in enumerate(trials))):
        raise ValueError("Missing, repeated or unordered worker clips")
    load_seconds = private["load_seconds"]
    if (isinstance(load_seconds, bool) or not isinstance(load_seconds, (float, int))
            or not math.isfinite(load_seconds) or load_seconds < 0):
        raise ValueError("Invalid load timing")
    rows = [score_trial(sample, trial, audio) for sample, trial, audio in zip(samples, trials, audio_info)]
    result = {"provenance": model, "runtime": private["runtime"], "decoding": private["decoding"],
              "timer_scope": private["timer_scope"], "load_seconds": load_seconds,
              "overall": summarize(rows),
              "datasets": {dataset: summarize([row for row in rows if row["dataset"] == dataset])
                           for dataset in sorted({row["dataset"] for row in rows})},
              "groups": [{"dataset": dataset, "group": group,
                          **summarize([row for row in rows if (row["dataset"], row["group"]) == (dataset, group)])}
                         for dataset, group in sorted({(row["dataset"], row["group"]) for row in rows})],
              "clips": rows}
    if "configuration" in private:
        result["configuration"] = private["configuration"]
    if "load_timer_scope" in private:
        result["load_timer_scope"] = private["load_timer_scope"]
    return result


def run_comparison(args, tilawi_pin, candidate_pin):
    cache = outside_checkout(args.cache)
    datasets, samples = load_datasets(args.manifest)
    models = {"tilawi": tilawi_pin["models"]["tilawi"], "mohammed": candidate_pin["models"]["mohammed"]}
    for key in args.models:
        for asset in models[key]["files"]:
            if not verify_asset(asset_path(cache, key, asset), asset):
                raise ValueError("Missing or changed model asset")
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "datasets": datasets, "environment": environment_info(),
              "normalization": NORMALIZATION_VERSION,
              "settings": {"warmups": 0, "repeats_per_clip": 1, "clip_order": "manifest order",
                           "reference": "dataset-supplied intended passage; no basmala removal",
                           "hypothesis_basmala_removed": False, "failure_policy": "abort; no report",
                           "model_loads": "once per model; clips processed sequentially"},
              "model_manifest_sha256": {name: sha256_file(HERE / name) for name in
                                        ("models.json", "fastconformer_models.json")},
              "runtime_lock_sha256": sha256_file(HERE / "fastconformer-requirements-linux-cpu.lock"),
              "implementation_sha256": {name: sha256_file(HERE / name) for name in
                  ("fastconformer.py", "fastconformer_worker.py", "batch.py", "batch_node_runner.mjs",
                   "benchmark.py", "scoring.py")},
              "limitations": ["Expected-passage text differences, not verified spoken-transcript WER",
                              "No learner mistake-detection or M0 acceptance claim",
                              "Fixed exploratory subsets; model training overlap unknown",
                              "Native CPU full-clip processing, not browser or live feedback latency",
                              "Different adapter formats and decoder types; not an isolated architecture comparison",
                              "Tilawi timer excludes CTC text decoding; NeMo timer includes RNNT text decoding",
                              "No warmups; descriptive timing statistics without confidence intervals"],
              "models": {}}
    with tempfile.TemporaryDirectory(prefix="quran-fastconformer-") as temporary:
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
            runner = (["node", str(HERE / "batch_node_runner.mjs")] if key == "tilawi"
                      else [sys.executable, str(HERE / "fastconformer_worker.py")])
            env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false",
                       OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", TORCH_FORCE_WEIGHTS_ONLY_LOAD="1",
                       WANDB_MODE="disabled", CUDA_VISIBLE_DEVICES="")
            result = subprocess.run(runner, input=json.dumps(config), text=True, capture_output=True,
                                    env=env, check=True, timeout=300 + 180 * len(samples))
            private = json.loads(result.stdout)
            report["models"][key] = model_summary(models[key], private, samples, audio_info)
            del private, result
            print(f"Completed {key}: {len(samples)} clips", flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("download", "run"):
        sub = commands.add_parser(command)
        sub.add_argument("--cache", required=True)
        sub.add_argument("--models", nargs="+", choices=MODEL_KEYS, default=list(MODEL_KEYS))
        if command == "run":
            sub.add_argument("--manifest", action="append", required=True)
            sub.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        args.models = list(dict.fromkeys(args.models))
        cache = outside_checkout(args.cache)
        tilawi_pin = validate_manifest(json.loads((HERE / "models.json").read_text()))
        candidate_pin = load_pin()
        if args.command == "download":
            if "tilawi" in args.models:
                download_models(cache, ["tilawi"], tilawi_pin)
            if "mohammed" in args.models:
                download_models(cache, ["mohammed"], candidate_pin)
        else:
            output = outside_checkout(args.output)
            if output.exists() or output == cache or cache in output.parents:
                raise ValueError("Output must be new and outside the model cache")
            report = run_comparison(args, tilawi_pin, candidate_pin)
            save_report(output, report)
            print("Saved aggregate report without audio, references, transcripts or speaker IDs.")
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        print("Comparison failed. Check pinned assets, manifests, runtime and audio limits. No report saved.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
