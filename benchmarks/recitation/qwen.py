#!/usr/bin/env python3
"""Compare raw Qwen3-ASR decoding with Tilawi on shared local clips and scoring."""

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import tempfile

from batch import load_datasets, save_report
from fastconformer import model_summary
from benchmark import (HERE, asset_path, decode_audio, download_models, environment_info,
                       outside_checkout, sha256_file, validate_manifest, verify_asset)
from scoring import NORMALIZATION_VERSION

MODEL_KEYS = ("tilawi", "qwen")


ALLOWED_ASSETS = frozenset({
    "model.safetensors", "config.json", "generation_config.json", "preprocessor_config.json",
    "processor_config.json", "tokenizer_config.json", "tokenizer.json", "vocab.json", "merges.txt",
    "special_tokens_map.json", "chat_template.json", "chat_template.jinja",
})


def load_pin():
    pin = json.loads((HERE / "qwen_models.json").read_text())
    if pin.get("schema_version") != 1 or set(pin.get("models", {})) != {"qwen"}:
        raise ValueError("Unsupported model pin")
    model = pin["models"]["qwen"]
    if (model["repo"] != "Qwen/Qwen3-ASR-0.6B"
            or not re.fullmatch(r"[0-9a-f]{40}", model["revision"])
            or not isinstance(model["files"], list) or not model["files"]):
        raise ValueError("Invalid model identity")
    seen = set()
    for asset in model["files"]:
        if (asset["path"] not in ALLOWED_ASSETS or asset["path"] in seen
                or type(asset["bytes"]) is not int or asset["bytes"] <= 0
                or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])):
            raise ValueError("Invalid model integrity metadata")
        seen.add(asset["path"])
    if not {"model.safetensors", "config.json", "preprocessor_config.json", "tokenizer_config.json"}.issubset(seen):
        raise ValueError("Missing required model or processor assets")
    return pin


def run_comparison(args, tilawi_pin, candidate_pin):
    cache = outside_checkout(args.cache)
    datasets, samples = load_datasets(args.manifest)
    models = {"tilawi": tilawi_pin["models"]["tilawi"], "qwen": candidate_pin["models"]["qwen"]}
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
                                        ("models.json", "qwen_models.json")},
              "runtime_lock_sha256": sha256_file(HERE / "qwen-requirements-linux-cpu.lock"),
              "implementation_sha256": {name: sha256_file(HERE / name) for name in
                  ("qwen.py", "qwen_worker.py", "fastconformer.py", "batch.py", "batch_node_runner.mjs",
                   "benchmark.py", "scoring.py")},
              "limitations": ["Expected-passage text differences, not verified spoken-transcript WER",
                              "No learner mistake-detection or M0 acceptance claim",
                              "Fixed exploratory subsets; model training overlap unknown",
                              "Native CPU full-clip processing, not browser or live feedback latency",
                              "Different adapter formats and decoder types; not an isolated architecture comparison",
                              "Tilawi timer excludes CTC text decoding; Qwen timer includes features, generation and text decoding",
                              "Qwen uses the pinned raw inference helper, bypassing default repetition cleanup and peak normalization",
                              "No warmups; descriptive timing statistics without confidence intervals"],
              "models": {}}
    with tempfile.TemporaryDirectory(prefix="quran-qwen-") as temporary:
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
                      else [sys.executable, str(HERE / "qwen_worker.py")])
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
            if "qwen" in args.models:
                download_models(cache, ["qwen"], candidate_pin)
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
