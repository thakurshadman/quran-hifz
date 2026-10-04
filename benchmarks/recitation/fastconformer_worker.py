"""Private offline NeMo worker; the caller captures and discards all hypotheses."""

import contextlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import random
import sys
import tarfile
import tempfile
import time

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                  TORCH_FORCE_WEIGHTS_ONLY_LOAD="1", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2",
                  TOKENIZERS_PARALLELISM="false", WANDB_MODE="disabled", CUDA_VISIBLE_DEVICES="")

from benchmark import asset_path, outside_checkout, sha256_file, verify_asset
from fastconformer import load_pin

# Explicit classes from the pinned checkpoint; never accept arbitrary Hydra imports.
ALLOWED_TARGETS = frozenset({
    "nemo.collections.asr.models.hybrid_rnnt_ctc_bpe_models.EncDecHybridRNNTCTCBPEModel",
    "nemo.collections.asr.modules.AudioToMelSpectrogramPreprocessor",
    "nemo.collections.asr.modules.SpectrogramAugmentation",
    "nemo.collections.asr.modules.ConformerEncoder",
    "nemo.collections.asr.modules.RNNTDecoder",
    "nemo.collections.asr.modules.RNNTJoint",
    "nemo.collections.asr.modules.ConvASRDecoder",
})
ARCHIVE_FILES = frozenset({
    "model_config.yaml", "model_weights.ckpt",
    "1e7bbe36b91a472896c99283bda08bf3_vocab.txt",
    "43c84e71237048ddab3bb273bdc00fa0_tokenizer.model",
    "e7a019581cd54cce88ac2acf8e4c54a3_tokenizer.vocab",
})


def check_targets(value, depth=0):
    if depth > 30:
        raise ValueError("Over-nested model configuration")
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("_target_", "target", "cls") and (not isinstance(item, str) or item not in ALLOWED_TARGETS):
                raise ValueError("Unapproved model configuration target")
            check_targets(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            check_targets(item, depth + 1)
    elif isinstance(value, str) and "${" in value:
        raise ValueError("Model configuration resolvers are not allowed")


def extract_archive(archive, destination):
    """Reject links, special files, traversal, duplicates and oversized archives."""
    with tarfile.open(archive, "r:*") as source:
        members = source.getmembers()
        if not members or len(members) > 128:
            raise ValueError("Unexpected archive member count")
        seen, total = set(), 0
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name
                    or not (member.isdir() or member.isfile()) or str(name) in seen
                    or (member.isdir() and str(name) != ".")
                    or (member.isfile() and str(name) not in ARCHIVE_FILES)):
                raise ValueError("Unsafe archive member")
            seen.add(str(name))
            total += member.size
            if member.size < 0 or total > 1_000_000_000:
                raise ValueError("Oversized model archive")
        source.extractall(destination, members=members, filter="data")
    if not all((destination / name).is_file() for name in ARCHIVE_FILES):
        raise ValueError("Missing model configuration, tokenizer or weights")


def transcription_text(result, hypothesis_type):
    """NeMo 2.5.3 RNNT returns a minimal Hypothesis even when that flag is false."""
    if not isinstance(result, list) or len(result) != 1:
        raise ValueError("Unexpected NeMo transcription batch")
    hypothesis = result[0]
    if not isinstance(hypothesis, hypothesis_type) or not isinstance(hypothesis.text, str):
        raise ValueError("Unexpected NeMo transcription result")
    return hypothesis.text


def run(config):
    import importlib.metadata
    import numpy as np
    import torch
    import yaml
    from omegaconf import OmegaConf, open_dict
    from nemo.collections.asr.models import EncDecHybridRNNTCTCBPEModel
    from nemo.collections.asr.parts.utils.rnnt_utils import Hypothesis
    from nemo.core.connectors.save_restore_connector import SaveRestoreConnector

    logging.disable(logging.CRITICAL)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    random.seed(0)
    np.random.seed(0)
    if config["model"] != "mohammed":
        raise ValueError("Unexpected adapter")
    directory = outside_checkout(config["directory"])
    model_pin = load_pin()["models"]["mohammed"]
    asset = model_pin["files"][0]
    # Verify again inside the worker before archive parsing or checkpoint loading.
    archive = asset_path(directory.parent, "mohammed", asset)
    if directory.name != "mohammed" or not verify_asset(archive, asset):
        raise ValueError("Model failed integrity verification")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="nemo-restore-", dir=directory.parent) as temporary:
        extracted = outside_checkout(temporary)
        extract_archive(archive, extracted)
        if (extracted / "model_config.yaml").stat().st_size > 2_000_000:
            raise ValueError("Oversized model configuration")
        raw_config = yaml.safe_load((extracted / "model_config.yaml").read_text())
        check_targets(raw_config)
        if (raw_config.get("target") != "nemo.collections.asr.models.hybrid_rnnt_ctc_bpe_models.EncDecHybridRNNTCTCBPEModel"
                or raw_config.get("sample_rate") != 16000
                or raw_config["preprocessor"].get("sample_rate") != 16000
                or raw_config["tokenizer"].get("type") != "bpe"):
            raise ValueError("Unexpected checkpoint model interface")
        model_config = OmegaConf.create(raw_config)
        with open_dict(model_config):
            model_config.train_ds = None
            model_config.validation_ds = None
            model_config.test_ds = None
            model_config.log_prediction = False
            model_config.tokenizer.dir = str(extracted)
            model_config.tokenizer.model_path = str(extracted / "43c84e71237048ddab3bb273bdc00fa0_tokenizer.model")
            model_config.tokenizer.vocab_path = str(extracted / "1e7bbe36b91a472896c99283bda08bf3_vocab.txt")
            model_config.tokenizer.spe_tokenizer_vocab = str(extracted / "e7a019581cd54cce88ac2acf8e4c54a3_tokenizer.vocab")
            model_config.decoding.greedy.use_cuda_graph_decoder = False
        if model_config.decoding.strategy != "greedy_batch" or model_config.decoding.greedy.max_symbols != 10:
            raise ValueError("Unexpected checkpoint decoding settings")
        connector = SaveRestoreConnector()
        connector.model_extracted_dir = str(extracted)
        model = EncDecHybridRNNTCTCBPEModel.restore_from(
            restore_path=str(archive), override_config_path=model_config,
            map_location=torch.device("cpu"), strict=True, save_restore_connector=connector).eval()
        model.change_decoding_strategy(decoding_cfg=model.cfg.decoding, decoder_type="rnnt", verbose=False)
        load_seconds = time.perf_counter() - started
        samples = []
        for sample in config["samples"]:
            audio = np.fromfile(sample["pcm"], dtype="<f4")
            try:
                started = time.perf_counter()
                with torch.inference_mode():
                    result = model.transcribe(audio=[audio], batch_size=1, num_workers=0,
                                              verbose=False, return_hypotheses=False)
                seconds = time.perf_counter() - started
                text = transcription_text(result, Hypothesis)
                samples.append({"index": sample["index"], "text": text, "seconds": seconds})
            finally:
                audio.fill(0)
        return {"load_seconds": load_seconds, "samples": samples,
                "load_timer_scope": "Archive extraction, configuration checks, model restoration and decoder setup; excludes imports and hash verification",
                "decoding": "RNNT greedy_batch; max_symbols 10; no passage prompt or matcher",
                "timer_scope": "NeMo transcribe call; includes features, encoder, RNNT decoding and text conversion",
                "configuration": {"decoder": "rnnt", "strategy": "greedy_batch", "max_symbols": 10,
                                  "batch_size": 1, "num_workers": 0, "weights_only": True,
                                  "device": "cpu", "seeds": {"torch": 0, "numpy": 0, "python": 0}, "cuda_graphs": False,
                                  "parameter_dtype": str(next(model.parameters()).dtype),
                                  "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                                  "checkpoint_nemo_version": raw_config.get("nemo_version"),
                                  "checkpoint_config_sha256": sha256_file(extracted / "model_config.yaml"),
                                  "attention_context": list(model_config.encoder.att_context_size),
                                  "decoding_config": OmegaConf.to_container(model.cfg.decoding, resolve=True, enum_to_str=True)},
                "runtime": {"python": sys.version.split()[0], "numpy": np.__version__,
                            "torch": torch.__version__, "torchaudio": importlib.metadata.version("torchaudio"),
                            "nemo_toolkit": importlib.metadata.version("nemo_toolkit")}}


if __name__ == "__main__":
    try:
        # NeMo may write status messages on stdout; keep the JSON protocol separate.
        with contextlib.redirect_stdout(sys.stderr):
            private = run(json.load(sys.stdin))
        print(json.dumps(private, allow_nan=False))
    except Exception:
        print("Local FastConformer inference failed.", file=sys.stderr)
        sys.exit(1)
