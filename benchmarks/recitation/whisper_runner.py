"""Offline Whisper worker. The caller captures and discards private hypotheses."""

import json
import os
import sys
import time

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")


def main():
    import numpy as np
    import torch
    import transformers
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    config = json.load(sys.stdin)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    audio = np.fromfile(config["pcm"], dtype="<f4")
    started = time.perf_counter()
    processor = WhisperProcessor.from_pretrained(config["directory"], local_files_only=True)
    model = WhisperForConditionalGeneration.from_pretrained(config["directory"], local_files_only=True).eval()
    model.generation_config.forced_decoder_ids = None
    decoder = [model.config.decoder_start_token_id] + [
        token for _, token in processor.get_decoder_prompt_ids(language="arabic", task="transcribe")]
    load_seconds = time.perf_counter() - started
    runs = []
    try:
        for index in range(config["warmups"] + config["repeats"]):
            started = time.perf_counter()
            features = processor(audio, sampling_rate=16000, return_tensors="pt", return_attention_mask=True)
            with torch.inference_mode():
                output = model.generate(input_features=features.input_features,
                                        attention_mask=features.attention_mask,
                                        decoder_input_ids=torch.tensor([decoder]),
                                        max_new_tokens=128, do_sample=False, num_beams=1)
            text = processor.batch_decode(output, skip_special_tokens=True)[0]
            seconds = time.perf_counter() - started
            if index >= config["warmups"]:
                runs.append({"text": text, "seconds": seconds})
        print(json.dumps({"load_seconds": load_seconds, "runs": runs,
                          "decoding": "greedy Arabic transcription; max_new_tokens 128; no reference prompt",
                          "timer_scope": "Whisper processor, generate and batch_decode; excludes model load",
                          "runtime": {"python": sys.version.split()[0], "numpy": np.__version__,
                                      "torch": torch.__version__, "transformers": transformers.__version__}}))
    finally:
        audio.fill(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Local inference failed.", file=sys.stderr)
        sys.exit(1)
