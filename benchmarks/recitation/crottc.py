#!/usr/bin/env python3
"""Local CROTTC k3 sound hypotheses. Output is private; never publish it."""
import argparse
import ast
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

from batch import save_report
from benchmark import HERE, outside_checkout, sha256_file, verify_asset, environment_info
from muaalem import decode_audio, decode_ctc_ids, quiet_library_logs


def vocabulary(path):
    result = {}
    for line in path.read_text().split('================')[0].splitlines():
        label, index = line.split(' => ')
        label, index = ast.literal_eval(label), int(index)
        if not isinstance(label, str) or index in result:
            raise ValueError('Invalid vocabulary')
        result[index] = label
    if result.get(0) != '<blank>':
        raise ValueError('Unexpected blank')
    return result


def render(ids, vocab):
    # The released 71-way head has only 70 vocabulary labels. Keep unknown IDs visible.
    return ' '.join(vocab.get(i, f'[UNMAPPED:{i}]') for i in ids)


def assets(cache, pins, download=False):
    for item in pins['files']:
        name = item['name']
        if Path(name).name != name:
            raise ValueError('Invalid asset name')
        target = outside_checkout(cache / name)
        if cache not in target.parents:
            raise ValueError('Invalid cache path')
        if verify_asset(target, item):
            continue
        if not download:
            raise ValueError('Missing or changed asset')
        cache.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as dst:
                temporary = Path(dst.name)
                with urllib.request.urlopen(item['url'], timeout=120) as src:
                    total = 0
                    while block := src.read(4 * 1024 * 1024):
                        total += len(block)
                        if total > item['bytes']:
                            raise ValueError('Oversized asset')
                        dst.write(block)
            if not verify_asset(temporary, item):
                raise ValueError('Asset mismatch')
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def load_model(cache):
    import torch
    from transformers import WavLMConfig, WavLMModel
    from speechbrain.lobes.models.VanillaNN import VanillaNN
    from speechbrain.lobes.models.transformer.Conformer import ConformerEncoder
    from speechbrain.nnet.linear import Linear

    config = WavLMConfig.from_json_file(cache / 'config.json')
    config.apply_spec_augment = False
    ssl = WavLMModel(config)
    weights = torch.load(cache / 'perceived_ssl.ckpt', map_location='cpu', weights_only=True)
    if not all(key.startswith('model.') for key in weights):
        raise ValueError('Unexpected SSL keys')
    ssl.load_state_dict({key[6:]: value for key, value in weights.items()}, strict=True)
    del weights
    model = torch.nn.ModuleList([
        torch.nn.Sequential(VanillaNN(input_shape=[None, None, 1024],
                                     activation=torch.nn.LeakyReLU, dnn_blocks=2, dnn_neurons=384),
                            torch.nn.LayerNorm(384)),
        ConformerEncoder(num_layers=2, nhead=8, d_ffn=384, d_model=384,
                         dropout=0.1, kernel_size=3, attention_type='RoPEMHA'),
        Linear(input_size=384, n_neurons=71), Linear(input_size=384, n_neurons=1)])
    model.load_state_dict(torch.load(cache / 'model.ckpt', map_location='cpu', weights_only=True), strict=True)
    return ssl.eval(), model.eval()


def run(args, cache, pins):
    if not 1 <= len(args.audio) <= 10:
        raise ValueError('Use one to ten recordings')
    inputs = [outside_checkout(p) for p in args.audio]
    assets(cache, pins)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', CUDA_VISIBLE_DEVICES='')
    report = {'privacy': 'PRIVATE raw phoneme hypotheses; delete after the agreed analysis',
              'pins': pins, 'environment': environment_info(),
              'implementation_sha256': {name: sha256_file(HERE / name) for name in
                  ('crottc.py', 'muaalem.py', 'batch.py', 'benchmark.py',
                   'crottc-pins.json', 'crottc-requirements-linux-cpu.lock')},
              'settings': {'device': 'cpu', 'dtype': 'float32', 'threads': 2, 'interop_threads': 1,
                           'seed': 0, 'warmups': 0, 'runs': 1, 'sample_rate': 16000,
                           'normalization': 'waveform layer_norm eps1e-5; no output normalization',
                           'decoding': 'greedy CTC collapse then remove blank0; no supplied reference',
                           'timer': 'normalization, model forward and decoding; excludes load/audio conversion'},
              'clips': []}
    with tempfile.TemporaryDirectory(prefix='crottc-private-') as tmp:
        directory = outside_checkout(tmp)
        decoded = []
        for index, audio in enumerate(inputs):
            pcm = directory / f'{index}.f32'
            decoded.append((pcm, decode_audio(audio, pcm)))
        with quiet_library_logs():
            import torch
            import numpy as np
            import speechbrain
            import transformers
            torch.set_num_threads(2)
            torch.set_num_interop_threads(1)
            torch.manual_seed(0)
            started = time.perf_counter()
            ssl, model = load_model(cache)
            report['load_seconds'] = time.perf_counter() - started
            report['runtime'] = {'torch': torch.__version__, 'speechbrain': speechbrain.__version__,
                                 'transformers': transformers.__version__, 'numpy': np.__version__}
            vocab = vocabulary(cache / 'tokenizer.ckpt')
            for index, (pcm, audio_info) in enumerate(decoded):
                audio = np.fromfile(pcm, dtype='<f4')
                try:
                    started = time.perf_counter()
                    with torch.inference_mode():
                        wav = torch.from_numpy(audio).unsqueeze(0)
                        wav = torch.nn.functional.layer_norm(wav, wav.shape[1:], eps=1e-5)
                        features = ssl(wav, attention_mask=None).last_hidden_state
                        projected = model[0](features)
                        encoded, _ = model[1](projected)
                        logits = model[2](encoded)
                        if logits.shape[-1] != 71 or not torch.isfinite(logits).all():
                            raise ValueError('Invalid logits')
                        ids = decode_ctc_ids(logits.argmax(-1)[0].tolist())
                    report['clips'].append({'index': index, **audio_info,
                                            'processing_seconds': time.perf_counter() - started,
                                            'frames': logits.shape[1], 'raw_phonemes': render(ids, vocab),
                                            'unmapped_ids': sorted(set(ids) - set(vocab))})
                finally:
                    audio.fill(0)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['download', 'run'])
    parser.add_argument('--cache', required=True)
    parser.add_argument('--audio', action='append')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        cache = outside_checkout(args.cache)
        pins = json.loads((HERE / 'crottc-pins.json').read_text())
        if args.command == 'download':
            assets(cache, pins, download=True)
            print('Verified CROTTC assets.')
        else:
            output = outside_checkout(args.output)
            if output.exists() or output == cache or cache in output.parents:
                raise ValueError('Use new private output outside cache')
            report = run(args, cache, pins)
            save_report(output, report)
            print('Saved private phoneme output; do not publish it.')
        return 0
    except Exception:
        print('CROTTC failed; check assets, runtime and inputs. No result saved.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
