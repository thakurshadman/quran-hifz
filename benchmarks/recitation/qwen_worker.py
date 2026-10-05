"""Private raw Qwen3-ASR worker; hypotheses exist only in captured pipes and memory."""

import contextlib
import json
import logging
import os
from pathlib import Path
import random
import sys
import time

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                  DO_NOT_TRACK="1", TORCH_FORCE_WEIGHTS_ONLY_LOAD="1", OMP_NUM_THREADS="2",
                  MKL_NUM_THREADS="2", TOKENIZERS_PARALLELISM="false", CUDA_VISIBLE_DEVICES="")

from benchmark import asset_path, outside_checkout, verify_asset
from qwen import load_pin


def validate_configs(directory):
    """Only pinned local registered classes; no repository-provided executable code."""
    config = json.loads((directory / "config.json").read_text())
    processor = json.loads((directory / "preprocessor_config.json").read_text())
    tokenizer = json.loads((directory / "tokenizer_config.json").read_text())
    if (config.get("model_type") != "qwen3_asr"
            or config.get("architectures") != ["Qwen3ASRForConditionalGeneration"]
            or processor.get("sampling_rate", 16000) != 16000
            or processor.get("feature_extractor_type") != "WhisperFeatureExtractor"
            or tokenizer.get("tokenizer_class") not in ("Qwen2Tokenizer", "Qwen2TokenizerFast")):
        raise ValueError("Unexpected model or processor interface")
    for filename in ("config.json", "preprocessor_config.json", "tokenizer_config.json", "processor_config.json"):
        path = directory / filename
        if not path.exists():
            continue
        value = json.loads(path.read_text())
        if value.get("auto_map"):
            raise ValueError("Repository-provided code is not allowed")
        if value.get("processor_class") not in (None, "Qwen3ASRProcessor"):
            raise ValueError("Unexpected processor class")


def transcription_text(result):
    """Return raw decoded text unchanged, including repetitions and whitespace."""
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], str):
        raise ValueError("Unexpected Qwen transcription result")
    return result[0]


def infer_raw(model, audio):
    """Pinned 0.0.6 helper bypasses transcribe's repetition/amplitude cleanup."""
    return transcription_text(model._infer_asr_transformers(contexts=[""], wavs=[audio], languages=["Arabic"]))


def run(config):
    if config["model"] != "qwen":
        raise ValueError("Unexpected adapter")
    directory = outside_checkout(config["directory"])
    if directory.name != "qwen":
        raise ValueError("Unexpected model directory")
    pin = load_pin()["models"]["qwen"]
    expected_files = {asset["path"] for asset in pin["files"]}
    # Every input asset is verified before model imports or weight loading.
    for asset in pin["files"]:
        if not verify_asset(asset_path(directory.parent, "qwen", asset), asset):
            raise ValueError("Model failed integrity verification")
    if any(path.name not in expected_files or not path.is_file() or path.is_symlink() for path in directory.iterdir()):
        raise ValueError("Unexpected unpinned local model asset")
    validate_configs(directory)

    import importlib.metadata
    import numpy as np
    import torch
    import transformers
    from qwen_asr import Qwen3ASRModel

    if importlib.metadata.version("qwen-asr") != "0.0.6":
        raise ValueError("Use the pinned raw-inference API version")
    logging.disable(logging.CRITICAL)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    random.seed(0)
    np.random.seed(0)
    torch.manual_seed(0)
    started = time.perf_counter()
    model = Qwen3ASRModel.from_pretrained(
        str(directory), dtype=torch.float32, device_map="cpu", attn_implementation="sdpa",
        local_files_only=True, trust_remote_code=False, use_safetensors=True,
        max_inference_batch_size=1, max_new_tokens=512)
    model.model.eval()
    if (model.backend != "transformers" or model.forced_aligner is not None
            or model.processor.feature_extractor.sampling_rate != 16000):
        raise ValueError("Unexpected Qwen backend or aligner")
    # The wrapper's generate() delegates to thinker.generate(), whose config is active.
    for component in (model.model, model.model.thinker):
        component.generation_config.do_sample = False
        component.generation_config.num_beams = 1
    generation = model.model.thinker.generation_config
    load_seconds = time.perf_counter() - started
    samples = []
    for sample in config["samples"]:
        audio = np.fromfile(sample["pcm"], dtype="<f4")
        try:
            if not 0 < audio.size <= 480000 or not np.isfinite(audio).all():
                raise ValueError("Invalid decoded PCM")
            started = time.perf_counter()
            with torch.inference_mode():
                text = infer_raw(model, audio)
            seconds = time.perf_counter() - started
            samples.append({"index": sample["index"], "text": text, "seconds": seconds})
        finally:
            audio.fill(0)
    return {"load_seconds": load_seconds, "samples": samples,
            "load_timer_scope": "Local model/processor loading and greedy configuration; excludes imports and integrity checks",
            "decoding": "Raw Qwen3-ASR Transformers helper; greedy Arabic; max_new_tokens 512; empty context",
            "timer_scope": "Official processor, generation and batch_decode; includes raw output validation; excludes PCM reads",
            "configuration": {
                "api": "qwen-asr 0.0.6 Qwen3ASRModel._infer_asr_transformers",
                "device": "cpu", "dtype": str(next(model.model.parameters()).dtype),
                "attention_implementation": "sdpa", "language": "Arabic", "context": "",
                "forced_aligner": False, "max_inference_batch_size": 1, "max_new_tokens": 512,
                "do_sample": generation.do_sample, "num_beams": generation.num_beams,
                "generation_config": json.loads(generation.to_json_string(ignore_metadata=False)),
                "generation_overrides": {"max_new_tokens": 512, "eos_token_id": [151645, 151643],
                                         "return_dict_in_generate": True},
                "seeds": {"python": 0, "numpy": 0, "torch": 0},
                "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                "model_eval": not model.model.training, "inference_mode": True,
                "parameter_count": sum(parameter.numel() for parameter in model.model.parameters()),
                "input_sample_rate": 16000, "input_format": "shared mono float32 PCM",
                "feature_extractor_sample_rate": model.processor.feature_extractor.sampling_rate,
                "wrapper_peak_normalization": False, "wrapper_resampling": False,
                "wrapper_chunking": False, "wrapper_repetition_cleanup": False,
                "batch_decode": {"skip_special_tokens": True, "clean_up_tokenization_spaces": False},
                "output": "Raw decoded generation; no official transcribe parser, stripping or repetition cleanup",
                "safe_loading": {"local_files_only": True, "trust_remote_code": False, "use_safetensors": True}},
            "runtime": {"python": sys.version.split()[0], "numpy": np.__version__,
                        "torch": torch.__version__, "transformers": transformers.__version__,
                        "qwen_asr": importlib.metadata.version("qwen-asr")}}


if __name__ == "__main__":
    try:
        with contextlib.redirect_stdout(sys.stderr):
            private = run(json.load(sys.stdin))
        print(json.dumps(private, allow_nan=False))
    except Exception:
        print("Local Qwen inference failed.", file=sys.stderr)
        sys.exit(1)
