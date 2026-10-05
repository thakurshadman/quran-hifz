#!/usr/bin/env python3
"""Test a pinned recognizer's response to exact repetition without inventing spoken truth."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile

from batch import load_datasets, save_report, score_trial, summarize
from benchmark import (HERE, asset_path, decode_audio, environment_info,
                       outside_checkout, sha256_file, validate_manifest, verify_asset)
from fastconformer import load_pin
from scoring import NORMALIZATION_VERSION, normalize

GAP_FRAMES = 4000
MAX_ORIGINAL_FRAMES = 236000
CATEGORIES = ("exact_two_copy_hypothesis", "exact_single_copy",
              "other_different", "unscorable_blank_baseline")
DECODING = "greedy CTC; blank 1024; no reference prompt or matcher"
TIMER_SCOPE = "ONNX session.run only; excludes CTC collapse and text decoding"
MOHAMMED_DECODING = "RNNT greedy_batch; max_symbols 10; no passage prompt or matcher"
MOHAMMED_TIMER_SCOPE = "NeMo transcribe call; includes features, encoder, RNNT decoding and text conversion"
MOHAMMED_LOAD_TIMER_SCOPE = "Archive extraction, configuration checks, model restoration and decoder setup; excludes imports and hash verification"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def validate_inputs(manifest_path, selection, public_lock):
    """Require the complete frozen 50-row source and the predeclared ten pairs."""
    manifest_path = outside_checkout(manifest_path)
    datasets, samples = load_datasets([manifest_path])
    raw = json.loads(manifest_path.read_text())
    source = public_lock["sources"]["openslr132"]
    frozen = public_lock["samples"]["openslr132"]
    if (public_lock["schema_version"] != 1 or len(frozen) != 50
            or raw["dataset"]["id"] != "openslr132"
            or raw["dataset"]["revision"] != source["revision"]
            or raw["dataset"].get("selection") != public_lock["selection"]["openslr132"]
            or len(raw["samples"]) != len(frozen)):
        raise ValueError("Prepared source does not match the frozen subset")
    for row, pin in zip(raw["samples"], frozen):
        if (row["id"] != f"row_{pin['row_index']}" or row["group"] != pin["group"]
                or row["audio_sha256"] != pin["audio_sha256"]
                or digest(row["reference_text"].encode("utf-8")) != pin["reference_sha256"]):
            raise ValueError("Source order, audio or unmodified passage changed")
    settings = selection["selection"]
    if (selection["schema_version"] != 1 or selection["source"] != source
            or selection["public_datasets_sha256"] != sha256_file(HERE / "public-datasets.json")
            or settings["sample_rate"] != 16000 or settings["gap_frames"] != GAP_FRAMES
            or settings["max_original_frames"] != MAX_ORIGINAL_FRAMES
            or settings["selected_pairs"] != 10 or settings["inferences"] != 20
            or len(selection["samples"]) != 10):
        raise ValueError("Unsupported repetition selection")
    by_id = {sample["id"]: (index, sample, pin)
             for index, (sample, pin) in enumerate(zip(samples, frozen))}
    chosen, last_index = [], -1
    for pin in selection["samples"]:
        index, sample, source_pin = by_id[pin["id"]]
        if (index <= last_index or pin["audio_sha256"] != source_pin["audio_sha256"]
                or pin["reference_sha256"] != source_pin["reference_sha256"]
                or type(pin["decoded_frames"]) is not int
                or not 0 < pin["decoded_frames"] <= MAX_ORIGINAL_FRAMES):
            raise ValueError("Repetition pins are duplicated, unordered or changed")
        for field in ("pcm_sha256", "repeated_pcm_sha256"):
            if not isinstance(pin[field], str) or not re.fullmatch(r"[0-9a-f]{64}", pin[field]):
                raise ValueError("Invalid decoded audio checksum")
        chosen.append({**sample, "pin": pin})
        last_index = index
    return datasets[0], chosen


def repeat_pcm(payload, gap_frames=GAP_FRAMES):
    """Copy the exact decoded samples twice, separated by 250 ms of zero samples."""
    if (type(gap_frames) is not int or gap_frames != GAP_FRAMES
            or not isinstance(payload, bytes) or len(payload) % 4
            or not 0 < len(payload) // 4 <= MAX_ORIGINAL_FRAMES):
        raise ValueError("Invalid repetition audio bounds")
    repeated = payload + bytes(gap_frames * 4) + payload
    if len(repeated) // 4 > 480000:
        raise ValueError("Repeated clip exceeds 30 seconds")
    return repeated


def classify_pair(single_text, repeated_text):
    single, repeated = normalize(single_text), normalize(repeated_text)
    if not single:
        category = "unscorable_blank_baseline"
    elif repeated == single * 2:
        category = "exact_two_copy_hypothesis"
    elif repeated == single:
        category = "exact_single_copy"
    else:
        category = "other_different"
    return {"category": category, "baseline_words": len(single), "repeated_words": len(repeated)}


def worker_metadata(private, model="tilawi"):
    """Allow only known metadata fields, never echo worker messages or hypotheses."""
    seconds = private["load_seconds"]
    if type(seconds) not in (float, int) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Invalid model-load timing")
    if model not in ("tilawi", "mohammed"):
        raise ValueError("Unknown repetition adapter")
    decoding = DECODING if model == "tilawi" else MOHAMMED_DECODING
    timer_scope = TIMER_SCOPE if model == "tilawi" else MOHAMMED_TIMER_SCOPE
    if private["decoding"] != decoding or private["timer_scope"] != timer_scope:
        raise ValueError("Unexpected worker decoding or timing protocol")
    runtime = private["runtime"]
    keys = (("node", "onnxruntime_node", "transformers_js") if model == "tilawi" else
            ("python", "numpy", "torch", "torchaudio", "nemo_toolkit"))
    if set(runtime) != set(keys) or any(
            not isinstance(runtime[key], str)
            or not re.fullmatch(r"v?\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?", runtime[key])
            for key in keys):
        raise ValueError("Invalid runtime versions")
    result = {"load_seconds": seconds, "decoding": decoding, "timer_scope": timer_scope,
              "runtime": {key: runtime[key] for key in keys}}
    if model == "mohammed":
        if private["load_timer_scope"] != MOHAMMED_LOAD_TIMER_SCOPE:
            raise ValueError("Unexpected model-load timing protocol")
        configuration = private["configuration"]
        expected = {"decoder": "rnnt", "strategy": "greedy_batch", "max_symbols": 10,
                    "batch_size": 1, "num_workers": 0, "weights_only": True, "device": "cpu",
                    "seeds": {"torch": 0, "numpy": 0, "python": 0}, "cuda_graphs": False,
                    "parameter_dtype": "torch.float32", "deterministic_algorithms": False,
                    "checkpoint_nemo_version": "2.0.0rc1", "attention_context": [-1, -1]}
        # Fixed configuration fields only; never expose arbitrary checkpoint metadata.
        for key, value in expected.items():
            if json.dumps(configuration[key], sort_keys=True) != json.dumps(value, sort_keys=True):
                raise ValueError("Unexpected pinned RNNT configuration")
        checkpoint_hash = configuration["checkpoint_config_sha256"]
        if not isinstance(checkpoint_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", checkpoint_hash):
            raise ValueError("Invalid checkpoint configuration checksum")
        if not isinstance(configuration["decoding_config"], dict):
            raise ValueError("Invalid decoder configuration")
        result["configuration"] = {
            **expected, "checkpoint_config_sha256": checkpoint_hash,
            "decoding_config_sha256": digest(json.dumps(configuration["decoding_config"],
                                                        sort_keys=True, allow_nan=False).encode("utf-8"))}
        result["load_timer_scope"] = MOHAMMED_LOAD_TIMER_SCOPE
    return result


def run_repetition(args, models, selection, public_lock):
    model = getattr(args, "model", "tilawi")
    if model not in ("tilawi", "mohammed"):
        raise ValueError("Unknown repetition adapter")
    cache = outside_checkout(args.cache)
    dataset, samples = validate_inputs(args.manifest, selection, public_lock)
    for asset in models["models"][model]["files"]:
        if not verify_asset(asset_path(cache, model, asset), asset):
            raise ValueError("Missing or changed model assets")
    model_manifest = "models.json" if model == "tilawi" else "fastconformer_models.json"
    # Capture the frozen protocol and code hashes before any model inference.
    report = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {**dataset, "prepared_manifest_samples": dataset["selected_samples"],
                    "selected_samples": len(samples)},
        "environment": environment_info(), "normalization": NORMALIZATION_VERSION,
        "public_datasets_sha256": sha256_file(HERE / "public-datasets.json"),
        "repetition_samples_sha256": sha256_file(HERE / "repetition-samples.json"),
        "model_manifest_file": model_manifest,
        "model_manifest_sha256": sha256_file(HERE / model_manifest),
        "npm_lock_sha256": sha256_file(HERE.parents[1] / "experiments/ikhlas-test/package-lock.json"),
        "implementation_sha256": {name: sha256_file(HERE / name) for name in
                                  ("repetition.py", "batch.py", "batch_node_runner.mjs", "benchmark.py", "scoring.py")},
        "settings": {"model_loads": 1, "warmups": 0, "runs_per_clip": 1,
                     "pair_order": "frozen source order; original then repeated",
                     "sample_rate": 16000, "channels": 1, "format": "float32 little-endian",
                     "gap_frames": GAP_FRAMES, "copies": 2, "failure_policy": "abort; no report",
                     "primary_comparison": "normalize(H(repeated)) == normalize(H(original)) * 2",
                     "auxiliary_reference": "dataset supplied passage; doubled for repeated clip",
                     "hypothesis_basmala_removed": False},
        "limitations": ["Exact audio duplication is not a natural spoken mistake or self-correction",
                        "A repeated baseline hypothesis is not independently verified spoken truth",
                        "Other-different outcomes do not establish that a repetition was lost",
                        "Supplied-passage differences are not ASR WER or learner error detection",
                        "No word omissions, substitutions, tajwid or streaming accuracy measured",
                        "Ten exploratory pairs; model training overlap and speaker diversity unknown",
                        "Native CPU full-clip inference, not browser or live feedback latency"],
        "model": {"key": model, "provenance": models["models"][model]}, "pairs": [],
    }
    if model == "mohammed":
        report["runtime_lock_sha256"] = sha256_file(HERE / "fastconformer-requirements-linux-cpu.lock")
        report["implementation_sha256"].update({name: sha256_file(HERE / name) for name in
                                               ("fastconformer.py", "fastconformer_worker.py")})
    with tempfile.TemporaryDirectory(prefix="quran-repetition-") as temporary:
        directory = outside_checkout(temporary)
        configurations, scoring_samples, audio_info = [], [], []
        for pair_index, sample in enumerate(samples):
            original = directory / f"{pair_index}-original.f32"
            repeated = directory / f"{pair_index}-repeated.f32"
            audio = decode_audio(sample["audio_path"], original)
            payload = original.read_bytes()
            pin = sample["pin"]
            if audio["samples"] != pin["decoded_frames"] or digest(payload) != pin["pcm_sha256"]:
                raise ValueError("Decoded source audio changed")
            repeated_payload = repeat_pcm(payload)
            if digest(repeated_payload) != pin["repeated_pcm_sha256"]:
                raise ValueError("Repeated audio changed")
            repeated.write_bytes(repeated_payload)
            for variant, pcm in enumerate((original, repeated)):
                configurations.append({"index": len(configurations), "pcm": str(pcm)})
                scoring_samples.append({**sample, "reference": sample["reference"] * (variant + 1)})
                audio_info.append(audio if variant == 0 else {
                    "seconds": len(repeated_payload) / 4 / 16000, "decode_seconds": 0})
            del payload, repeated_payload
        report["audio"] = {"inferences": len(configurations),
                           "total_seconds": sum(item["seconds"] for item in audio_info),
                           "total_decode_seconds": sum(item["decode_seconds"] for item in audio_info)}
        config = {"model": model, "directory": str(cache / model), "samples": configurations}
        env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false",
                   OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
        runner = (["node", str(HERE / "batch_node_runner.mjs")] if model == "tilawi" else
                  [sys.executable, str(HERE / "fastconformer_worker.py")])
        if model == "mohammed":
            env.update(TORCH_FORCE_WEIGHTS_ONLY_LOAD="1", WANDB_MODE="disabled", CUDA_VISIBLE_DEVICES="")
        result = subprocess.run(runner, input=json.dumps(config),
                                text=True, capture_output=True, env=env, check=True, timeout=3900)
        private = json.loads(result.stdout)
        trials = private["samples"]
        if (not isinstance(trials, list) or len(trials) != 20 or any(
                type(trial["index"]) is not int or trial["index"] != index
                for index, trial in enumerate(trials))):
            raise ValueError("Worker returned missing, repeated or unordered clips")
        report["model"].update(worker_metadata(private, model))
        # Existing scorer validates finite timings and bounded text for every row.
        rows = [score_trial(sample, trial, audio)
                for sample, trial, audio in zip(scoring_samples, trials, audio_info)]
        metric_keys = ("reference_words", "hypothesis_words", "substitutions", "deletions", "insertions",
                       "text_difference_pct", "exact_match", "audio_seconds", "inference_seconds", "real_time_factor")
        for index, sample in enumerate(samples):
            first, second = index * 2, index * 2 + 1
            report["pairs"].append({"input": {key: sample["pin"][key] for key in
                ("id", "audio_sha256", "reference_sha256", "decoded_frames", "pcm_sha256", "repeated_pcm_sha256")},
                "primary": classify_pair(trials[first]["text"], trials[second]["text"]),
                "auxiliary_original": {key: rows[first][key] for key in metric_keys},
                "auxiliary_repeated": {key: rows[second][key] for key in metric_keys}})
        report["primary"] = {"pairs": len(samples), **{category: sum(
            pair["primary"]["category"] == category for pair in report["pairs"]) for category in CATEGORIES}}
        report["primary"]["scorable_pairs"] = len(samples) - report["primary"]["unscorable_blank_baseline"]
        report["auxiliary"] = {"original": summarize(rows[::2]), "repeated": summarize(rows[1::2])}
        del private, result, trials
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", choices=("tilawi", "mohammed"), default="tilawi")
    args = parser.parse_args(argv)
    try:
        cache, output = outside_checkout(args.cache), outside_checkout(args.output)
        if output.exists() or output == cache or cache in output.parents:
            raise ValueError("Output must be new and outside the model cache")
        models = validate_manifest(json.loads((HERE / "models.json").read_text()))
        if args.model == "mohammed":
            models["models"].update(load_pin()["models"])
        selection = json.loads((HERE / "repetition-samples.json").read_text())
        public_lock = json.loads((HERE / "public-datasets.json").read_text())
        report = run_repetition(args, models, selection, public_lock)
        save_report(output, report)
        print("Saved repetition counts without audio, text, local paths or speaker IDs.")
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, IndexError, subprocess.SubprocessError):
        print("Repetition test failed. Check frozen inputs, audio limits and local dependencies. No report saved.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
