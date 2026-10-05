#!/usr/bin/env python3
"""Offline Muaalem raw phonemes; explicit outputs are private, never benchmark publications."""

import argparse
import contextlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time
import types
import urllib.request

from batch import save_report
from benchmark import HERE, environment_info, outside_checkout, sha256_file, verify_asset

MODEL_FILES = {"config.json", "preprocessor_config.json", "vocab.json", "model.safetensors"}
SOURCE_FILES = ("configuration_multi_level_ctc.py", "modeling_multi_level_ctc.py")


def decode_ctc_ids(frameids, blank=0):
    """Collapse adjacent equal frame IDs, then remove blank; retain separated repeats."""
    if type(blank) is not int or blank < 0:
        raise ValueError("Invalid CTC blank")
    result, previous = [], None
    for token in frameids:
        if type(token) is not int or token < 0:
            raise ValueError("Invalid CTC token")
        if token != previous and token != blank:
            result.append(token)
        previous = token
    return result


def phoneme_text(ids, vocab):
    """Keep every emitted QPS symbol, including vowels and recitation marks."""
    if (not isinstance(vocab, dict) or vocab.get("[PAD]") != 0
            or any(not isinstance(symbol, str) or not symbol or type(token) is not int or token < 0
                   for symbol, token in vocab.items()) or len(set(vocab.values())) != len(vocab)):
        raise ValueError("Invalid phoneme vocabulary")
    reverse = {token: symbol for symbol, token in vocab.items()}
    if any(type(token) is not int or token == 0 or token not in reverse for token in ids):
        raise ValueError("Unexpected emitted phoneme token")
    return "".join(reverse[token] for token in ids)


def validate_pins(pins):
    if pins.get("schema_version") != 1:
        raise ValueError("Unsupported Muaalem pins")
    expected = {"model": ("obadx/muaalem-model-v3_2", MODEL_FILES),
                "source": ("obadx/quran-muaalem", set(SOURCE_FILES))}
    for kind, (repo, filenames) in expected.items():
        group = pins[kind]
        if group["repo"] != repo or not re.fullmatch(r"[0-9a-f]{40}", group["revision"]):
            raise ValueError("Unexpected upstream identity")
        files = group["files"]
        if not isinstance(files, list) or len(files) != len(filenames):
            raise ValueError("Unexpected asset set")
        names = []
        for asset in files:
            name = asset["path"] if kind == "model" else asset["local_name"]
            if name not in filenames or (kind == "source" and asset["path"] != f"src/quran_muaalem/modeling/{name}"):
                raise ValueError("Unexpected asset path")
            names.append(name)
            if (type(asset["bytes"]) is not int or asset["bytes"] <= 0
                    or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])):
                raise ValueError("Invalid asset checksum metadata")
        if set(names) != filenames:
            raise ValueError("Missing or repeated pinned asset")
    return pins


def cache_file(cache, kind, asset):
    name = asset["path"] if kind == "model" else asset["local_name"]
    candidate = cache / kind / name
    resolved = outside_checkout(candidate)
    if cache not in resolved.parents or candidate.is_symlink():
        raise ValueError("Asset escapes cache")
    return candidate


def verify_cache(cache, pins):
    for kind in ("model", "source"):
        for asset in pins[kind]["files"]:
            if not verify_asset(cache_file(cache, kind, asset), asset):
                raise ValueError("Missing or changed pinned asset")


def download(cache, pins):
    for kind in ("model", "source"):
        group = pins[kind]
        for asset in group["files"]:
            target = cache_file(cache, kind, asset)
            if verify_asset(target, asset):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            base = (f"https://huggingface.co/{group['repo']}/resolve/{group['revision']}/" if kind == "model"
                    else f"https://raw.githubusercontent.com/{group['repo']}/{group['revision']}/")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".download-", delete=False) as output:
                    temporary = Path(output.name)
                    with urllib.request.urlopen(base + asset["path"], timeout=120) as response:
                        total = 0
                        while block := response.read(1024 * 1024):
                            total += len(block)
                            if total > asset["bytes"]:
                                raise ValueError("Asset exceeds pinned size")
                            output.write(block)
                if not verify_asset(temporary, asset):
                    raise ValueError("Downloaded asset differs from pin")
                temporary.replace(target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def decode_audio(audio, pcm):
    probe = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                            "-show_entries", "format=duration", "-of", "json", str(audio)],
                           capture_output=True, check=True, timeout=30)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if not math.isfinite(duration) or not 0 < duration <= 60:
        raise ValueError("Use nonempty audio of at most 60 seconds")
    started = time.perf_counter()
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(audio),
                    "-t", "60.0000625", "-ac", "1", "-ar", "16000", "-f", "f32le", str(pcm)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=120)
    size = pcm.stat().st_size
    if size % 4 or not 0 < size // 4 <= 960000:
        raise ValueError("Decoded audio exceeds limit")
    return {"samples": size // 4, "seconds": size / 64000,
            "decode_seconds": time.perf_counter() - started}


def load_source(cache, pins):
    """Execute only the two verified modules, without upstream __init__ or remote-code loading."""
    package_name = "_muaalem_audited_model"
    package = types.ModuleType(package_name)
    package.__path__ = [str(cache / "source")]
    sys.modules[package_name] = package
    for name in SOURCE_FILES:
        asset = next(asset for asset in pins["source"]["files"] if asset["local_name"] == name)
        source = cache_file(cache, "source", asset)
        if not verify_asset(source, asset):
            raise ValueError("Audited source changed")
        module_name = f"{package_name}.{source.stem}"
        spec = importlib.util.spec_from_file_location(module_name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        # Compile verified source directly; do not execute an unchecked cached .pyc.
        exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
    return sys.modules[f"{package_name}.modeling_multi_level_ctc"].Wav2Vec2BertForMultilevelCTC


@contextlib.contextmanager
def quiet_library_logs():
    """Discard Python and native-library logs, including local input paths."""
    with open(os.devnull, "w") as sink:
        saved = [os.dup(1), os.dup(2)]
        try:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
        finally:
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            for descriptor in saved:
                os.close(descriptor)


def run(args, pins):
    cache = outside_checkout(args.cache)
    if not 1 <= len(args.audio) <= 10:
        raise ValueError("Use one to ten recordings")
    inputs = [outside_checkout(path) for path in args.audio]
    if any(not path.is_file() for path in inputs):
        raise ValueError("Missing audio input")
    verify_cache(cache, pins)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2",
                      WANDB_MODE="disabled", CUDA_VISIBLE_DEVICES="")
    report = {"schema_version": 1, "privacy": "PRIVATE: contains raw phoneme hypotheses; do not publish",
              "environment": environment_info(),
              "pins": pins, "pins_sha256": sha256_file(HERE / "muaalem-pins.json"),
              "runtime_lock_sha256": sha256_file(HERE / "qwen-requirements-linux-cpu.lock"),
              "implementation_sha256": {name: sha256_file(HERE / name) for name in
                                         ("muaalem.py", "batch.py", "benchmark.py")},
              "settings": {"sample_rate": 16000, "channels": 1, "format": "float32 little-endian",
                           "model_loads": 1, "warmups": 0, "runs_per_clip": 1,
                           "device": "cpu", "dtype": "float32", "attention": "eager",
                           "intra_op_threads": 2, "inter_op_threads": 1, "seed": 0,
                           "decoding": "greedy phoneme-head CTC; collapse consecutive IDs then remove blank 0",
                           "normalization": "none; retain all QPS symbols; no prompt, reference or alignment"},
              "timer_scope": "Feature extraction, forward pass, argmax and raw CTC decoding; excludes model load",
              "limitations": ["Raw QPS phonemes are hypotheses, not verified Quran text or tajwid judgments",
                              "No spoken reference, error rate, mistake detection or correctness score",
                              "CPU whole-recording inference, not streaming or phone timing"], "clips": []}
    with tempfile.TemporaryDirectory(prefix="muaalem-private-") as temporary:
        directory = outside_checkout(temporary)
        decoded = []
        for index, audio in enumerate(inputs):
            pcm = directory / f"{index}.f32"
            decoded.append((pcm, decode_audio(audio, pcm)))
        with quiet_library_logs():
            import numpy as np
            import torch
            import transformers
            from transformers import SeamlessM4TFeatureExtractor

            torch.set_num_threads(2)
            torch.set_num_interop_threads(1)
            torch.manual_seed(0)
            np.random.seed(0)
            random.seed(0)
            model_class = load_source(cache, pins)
            started = time.perf_counter()
            model, loading = model_class.from_pretrained(
                cache / "model", local_files_only=True, use_safetensors=True, dtype=torch.float32,
                output_loading_info=True, attn_implementation="eager")
            if any(loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
                raise ValueError("Checkpoint did not load exactly")
            model.eval()
            extractor = SeamlessM4TFeatureExtractor.from_pretrained(cache / "model", local_files_only=True)
            vocab = json.loads((cache / "model/vocab.json").read_text())["phonemes"]
            phoneme_text([], vocab)
            if (model.config.pad_token_id != 0 or model.config.level_to_vocab_size["phonemes"] != len(vocab)
                    or extractor.sampling_rate != 16000):
                raise ValueError("Unexpected phoneme model interface")
            report["load_seconds"] = time.perf_counter() - started
            report["runtime"] = {"python": sys.version.split()[0], "numpy": np.__version__,
                                 "torch": torch.__version__, "transformers": transformers.__version__}
            report["deterministic_algorithms"] = torch.are_deterministic_algorithms_enabled()
            for index, (pcm, audio_info) in enumerate(decoded):
                audio = np.fromfile(pcm, dtype="<f4")
                try:
                    started = time.perf_counter()
                    features = extractor(audio, sampling_rate=16000, return_tensors="pt", truncation=False)
                    with torch.inference_mode():
                        logits = model(**features).logits["phonemes"]
                    if (logits.ndim != 3 or logits.shape[0] != 1 or logits.shape[2] != len(vocab)
                            or logits.shape[1] < 1 or not torch.isfinite(logits).all().item()):
                        raise ValueError("Invalid phoneme logits")
                    ids = decode_ctc_ids(logits.argmax(dim=-1)[0].tolist())
                    text = phoneme_text(ids, vocab)
                    seconds = time.perf_counter() - started
                    report["clips"].append({"index": index, **audio_info, "logit_frames": logits.shape[1],
                                            "phoneme_tokens": len(ids), "raw_phonemes": text,
                                            "inference_seconds": seconds})
                finally:
                    audio.fill(0)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("download", "run"):
        sub = commands.add_parser(command)
        sub.add_argument("--cache", required=True)
        if command == "run":
            sub.add_argument("--audio", action="append", required=True)
            sub.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        pins = validate_pins(json.loads((HERE / "muaalem-pins.json").read_text()))
        cache = outside_checkout(args.cache)
        if args.command == "download":
            download(cache, pins)
            print("Verified Muaalem model and audited source assets.")
        else:
            output = outside_checkout(args.output)
            if output.exists() or output == cache or cache in output.parents:
                raise ValueError("Output must be new and outside model cache")
            report = run(args, pins)
            save_report(output, report)
            print("Saved private phoneme output. Do not publish this file.")
        return 0
    except Exception:
        print("Muaalem failed. Check frozen assets, runtime and audio limits. No output saved.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
