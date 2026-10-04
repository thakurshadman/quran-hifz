#!/usr/bin/env python3
"""Reproducible local Al-Ikhlas comparison, with aggregate-only reports."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from scoring import NORMALIZATION_VERSION, edit_counts, normalize, reference_words

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parents[1]
MODEL_KEYS = ("tilawi", "tiny", "tarteel", "quran-turbo")
REFERENCE_FILES = {"quran.json", "TANZIL-NOTICE.txt", "SHA256SUMS"}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def outside_checkout(path):
    resolved = Path(path).expanduser().resolve()
    if resolved == CHECKOUT or CHECKOUT in resolved.parents:
        raise ValueError("Audio, cache and output must be outside the checkout")
    if any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
        raise ValueError("Private inputs and outputs must be outside any git checkout")
    return resolved


def validate_manifest(data):
    if data.get("schema_version") != 1 or set(data.get("models", {})) != set(MODEL_KEYS):
        raise ValueError("Unsupported manifest")
    for model in data["models"].values():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", model["repo"]):
            raise ValueError("Invalid model repository")
        if not re.fullmatch(r"[0-9a-f]{40}", model["revision"]):
            raise ValueError("Model revision must be immutable")
        if not isinstance(model["files"], list) or not model["files"]:
            raise ValueError("Missing model assets")
        seen = set()
        for asset in model["files"]:
            path = PurePosixPath(asset["path"])
            if (path.is_absolute() or ".." in path.parts or "\\" in asset["path"]
                    or not path.parts or str(path) != asset["path"] or asset["path"] in seen):
                raise ValueError("Invalid or duplicate asset path")
            seen.add(asset["path"])
            if not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]) or not isinstance(asset["bytes"], int) or asset["bytes"] <= 0:
                raise ValueError("Invalid asset integrity metadata")
    if not {"quran.json", "TANZIL-NOTICE.txt"}.issubset(
            {f["path"] for f in data["models"]["tilawi"]["files"]}):
        raise ValueError("Missing reference provenance")
    return data


def verify_asset(path, asset):
    path = Path(path)
    return (path.is_file() and not path.is_symlink() and path.stat().st_size == asset["bytes"]
            and sha256_file(path) == asset["sha256"])


def asset_path(cache, key, asset):
    candidate = cache / key / asset["path"]
    resolved = outside_checkout(candidate)
    if cache not in resolved.parents or candidate.is_symlink():
        raise ValueError("Cache asset escapes cache directory")
    return candidate


def needed_assets(manifest, selected):
    for key, model in manifest["models"].items():
        for asset in model["files"]:
            if key in selected or (key == "tilawi" and asset["path"] in REFERENCE_FILES):
                yield key, model, asset


def download_models(cache, selected, manifest):
    cache.mkdir(parents=True, exist_ok=True)
    for key, model, asset in needed_assets(manifest, selected):
        target = asset_path(cache, key, asset)
        if verify_asset(target, asset):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        # Frozen public GET: never attach user audio, credentials or private headers.
        url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/"
        url += urllib.parse.quote(asset["path"], safe="/")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".download-", delete=False) as output:
                temporary = Path(output.name)
                with urllib.request.urlopen(url, timeout=120) as response:
                    total = 0
                    while block := response.read(1024 * 1024):
                        total += len(block)
                        if total > asset["bytes"]:
                            raise ValueError("Downloaded asset exceeds expected size")
                        output.write(block)
            if not verify_asset(temporary, asset):
                raise ValueError("Downloaded asset failed integrity verification")
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(f"Verified {key}: {asset['path']}", flush=True)


def decode_audio(audio, pcm):
    """Bound decoding to 30 seconds plus one sample; reject rather than truncate."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_entries", "format=duration",
                            "-of", "json", str(audio)], capture_output=True, check=True, timeout=30)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if not math.isfinite(duration) or not 0 < duration <= 30:
        raise ValueError("Use a nonempty recording of at most 30 seconds")
    started = time.perf_counter()
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(audio),
                    "-t", "30.0000625", "-ac", "1", "-ar", "16000", "-f", "f32le", str(pcm)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=120)
    size = pcm.stat().st_size
    if size % 4 or not 0 < size // 4 <= 480000:
        raise ValueError("Decoded recording exceeds bounds")
    return {"sample_rate": 16000, "channels": 1, "samples": size // 4,
            "seconds": size / 4 / 16000, "format": "float32 little-endian",
            "decode_seconds": time.perf_counter() - started}


def environment_info():
    def command(args):
        try:
            return subprocess.check_output(args, cwd=CHECKOUT, stderr=subprocess.DEVNULL,
                                           text=True, timeout=15).strip()
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
    cpu = platform.processor() or "unknown"
    memory_bytes = None
    if Path("/proc/cpuinfo").is_file():
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    if hasattr(os, "sysconf"):
        try:
            memory_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError):
            pass
    return {"os": platform.system(), "os_release": platform.release(), "architecture": platform.machine(),
            "cpu": cpu, "logical_cpus": os.cpu_count(), "physical_memory_bytes": memory_bytes,
            "python": platform.python_version(), "ffmpeg": command(["ffmpeg", "-version"]).splitlines()[0],
            "git_commit": command(["git", "rev-parse", "HEAD"]),
            "working_tree_dirty": bool(command(["git", "status", "--porcelain"])),
            "threads": {"intra_op": 2, "inter_op": 1}, "execution": "native CPU; not browser/WASM"}


def run_models(args, manifest):
    cache = outside_checkout(args.cache)
    audio = outside_checkout(args.audio)
    if not audio.is_file():
        raise ValueError("Audio input is not a file")
    for key, _, asset in needed_assets(manifest, args.models):
        if not verify_asset(asset_path(cache, key, asset), asset):
            raise ValueError("Missing or changed cached assets; run download first")
    reference = reference_words(json.loads((cache / "tilawi/quran.json").read_text()), args.basmala)
    report = {"schema_version": 1, "input_sha256": sha256_file(audio),
              "environment": environment_info(), "normalization": NORMALIZATION_VERSION,
              "settings": {"basmala": args.basmala, "warmups": args.warmups, "repeats": args.repeats,
                           "reference_surah": 112, "reference_ayahs": [1, 2, 3, 4],
                           "hypothesis_basmala_removed": False, "reference_words": len(reference)},
              "manifest_sha256": sha256_file(HERE / "models.json"),
              "reference_provenance": {"repo": manifest["models"]["tilawi"]["repo"],
                                       "revision": manifest["models"]["tilawi"]["revision"],
                                       "files": [f for f in manifest["models"]["tilawi"]["files"]
                                                 if f["path"] in REFERENCE_FILES]},
              "implementation_sha256": {name: sha256_file(HERE / name) for name in
                                         ("benchmark.py", "scoring.py", "node_runner.mjs", "whisper_runner.py")},
              "limitations": ["Single recording, no independently annotated spoken transcript",
                              "Text difference from expected passage, not ASR WER or recitation accuracy",
                              "Full-clip native CPU inference, not live feedback latency",
                              "Median descriptive only; no tail-latency or statistical confidence claim"],
              "models": {}}
    with tempfile.TemporaryDirectory(prefix="quran-benchmark-") as temporary:
        temporary = outside_checkout(temporary)
        pcm = temporary / "audio.f32"
        report["audio"] = decode_audio(audio, pcm)
        for key in args.models:
            configuration = {"model": key, "directory": str(cache / key), "pcm": str(pcm),
                             "warmups": args.warmups, "repeats": args.repeats}
            runner = (["node", str(HERE / "node_runner.mjs")] if key in ("tilawi", "tiny")
                      else [sys.executable, str(HERE / "whisper_runner.py")])
            env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false")
            result = subprocess.run(runner, input=json.dumps(configuration), text=True, capture_output=True,
                                    env=env, check=True, timeout=1800)
            private = json.loads(result.stdout)
            runs = []
            if len(private["runs"]) != args.repeats:
                raise ValueError("Unexpected worker repeat count")
            for trial in private["runs"]:
                seconds = trial["seconds"]
                if not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or seconds < 0:
                    raise ValueError("Invalid inference timing")
                if not isinstance(trial["text"], str) or len(trial["text"]) > 20000:
                    raise ValueError("Invalid recognizer output")
                hypothesis = normalize(trial["text"])
                counts = edit_counts(reference, hypothesis)
                runs.append({**counts, "hypothesis_words": len(hypothesis),
                             "text_difference_pct": round(100 * sum(counts.values()) / len(reference), 4),
                             "inference_seconds": seconds,
                             "real_time_factor": seconds / report["audio"]["seconds"]})
            report["models"][key] = {"provenance": manifest["models"][key],
                                     "runtime": private["runtime"], "decoding": private["decoding"],
                                     "timer_scope": private["timer_scope"],
                                     "load_seconds": private["load_seconds"], "runs": runs,
                                     "median_inference_seconds": statistics.median(r["inference_seconds"] for r in runs)}
            # Hypotheses were only in subprocess pipes and process memory, never files/logs.
            del private, result
            print(f"Completed {key}", flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("download", "run"):
        sub = subcommands.add_parser(command)
        sub.add_argument("--models", nargs="+", choices=MODEL_KEYS, default=list(MODEL_KEYS))
        sub.add_argument("--cache", required=True)
        if command == "run":
            sub.add_argument("--audio", required=True)
            sub.add_argument("--output", required=True)
            sub.add_argument("--basmala", choices=("include", "exclude"), default="exclude")
            sub.add_argument("--warmups", type=int, default=0)
            sub.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        manifest = validate_manifest(json.loads((HERE / "models.json").read_text()))
        args.models = list(dict.fromkeys(args.models))
        cache = outside_checkout(args.cache)
        if args.command == "download":
            download_models(cache, args.models, manifest)
        else:
            if not 0 <= args.warmups <= 20 or not 1 <= args.repeats <= 100:
                raise ValueError("Use 0–20 warmups and 1–100 repeats")
            output = outside_checkout(args.output)
            if output.exists() or cache == output or cache in output.parents:
                raise ValueError("Output must be a new file outside the model cache")
            report = run_models(args, manifest)
            # Exclusive creation prevents overwriting existing audio, models or results.
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as destination:
                json.dump(report, destination, indent=2)
                destination.write("\n")
            print("Saved aggregate-only report.")
        return 0
    except ValueError:
        print("Invalid input, reference or asset integrity. Check paths, bounds and frozen cache.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Local processing timed out; no report was saved.", file=sys.stderr)
    except subprocess.CalledProcessError:
        print("Local audio/inference tool failed. Check dependencies and available memory; no report saved.", file=sys.stderr)
    except (OSError, KeyError, TypeError):
        print("Local file, dependency or download unavailable. Check setup and cache; no report saved.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
