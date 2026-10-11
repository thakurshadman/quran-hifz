#!/usr/bin/env python3
"""Conservative sound alignment probe, not a recitation grader."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

from benchmark import HERE, outside_checkout, sha256_file
from batch import save_report


def align_window(reference, hypothesis, target_start, target_end, context_budget=2):
    """Fit a reference window anywhere; require one optimal path before diagnosing."""
    n, m = len(reference), len(hypothesis)
    if not (0 < target_start < target_end < n <= 128 and 0 < m <= 4096):
        return {'status': 'unsure', 'reason': 'invalid_or_missing_context'}
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    count = [[1] * (m + 1)] + [[0] * (m + 1) for _ in range(n)]
    trace = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0], count[i][0], trace[i][0] = i, 1, 'delete'
        for j in range(1, m + 1):
            same = reference[i - 1] == hypothesis[j - 1]
            choices = [(cost[i-1][j-1] + (not same), 'match' if same else 'substitute', i-1, j-1),
                       (cost[i-1][j] + 1, 'delete', i-1, j),
                       (cost[i][j-1] + 1, 'insert', i, j-1)]
            best = min(x[0] for x in choices)
            winners = [x for x in choices if x[0] == best]
            cost[i][j] = best
            count[i][j] = min(2, sum(count[a][b] for _, _, a, b in winners))
            trace[i][j] = winners[0][1]
    best = min(cost[n])
    ends = [j for j in range(m + 1) if cost[n][j] == best]
    result = {'edit_cost': best, 'reference_groups': n}
    if sum(count[n][j] for j in ends) != 1:
        return {**result, 'status': 'unsure', 'reason': 'ambiguous_alignment'}
    i, j = n, ends[0]
    target = {'match': 0, 'delete': 0, 'substitute': 0, 'insert': 0}
    context_edits = 0
    context_matches = [0, 0]
    while i:
        op = trace[i][j]
        in_target = target_start <= i-1 < target_end if op != 'insert' else target_start <= i <= target_end
        if in_target:
            target[op] += 1
        elif op != 'match':
            context_edits += 1
        else:
            context_matches[0 if i-1 < target_start else 1] += 1
        if op in ('match', 'substitute'):
            i, j = i-1, j-1
        elif op == 'delete':
            i -= 1
        else:
            j -= 1
    result.update(target_operations=target, context_edits=context_edits)
    if not all(context_matches):
        return {**result, 'status': 'unsure', 'reason': 'unmatched_context_side'}
    if context_edits > context_budget:
        return {**result, 'status': 'unsure', 'reason': 'noisy_context'}
    if target['substitute'] or target['insert'] or not target['match']:
        return {**result, 'status': 'unsure', 'reason': 'mixed_or_missing_target'}
    if target['delete']:
        return {**result, 'status': 'possible_omission', 'reason': 'deletion_only_target_difference'}
    return {**result, 'status': 'no_target_difference', 'reason': 'exact_target_in_unique_alignment'}


def verified_package(protocol):
    spec = importlib.util.find_spec('quran_transcript')
    root = Path(spec.origin).parent
    for name, digest in protocol['package_sha256'].items():
        if sha256_file(root / name) != digest:
            raise ValueError('Reference package changed')
    return root


def make_reference(protocol, sura, aya, word):
    verified_package(protocol)
    from quran_transcript import Aya, MoshafAttributes, quran_phonetizer
    from quran_transcript.phonetics.sifa import chunck_phonemes
    text = Aya(sura, aya).get().uthmani
    words = list(re.finditer(r'\S+', text))
    # One preceding word and one following word, both within this ayah.
    if not 2 <= word <= len(words)-1:
        raise ValueError('Target needs words on both sides within one ayah')
    converted = quran_phonetizer(text, MoshafAttributes(**protocol['moshaf']),
                                 remove_spaces=True, sura_idx=sura)
    spans = []
    for w in words[word-2:word+1]:
        positions = [p.pos for p in converted.mappings[w.start():w.end()] if p is not None and p.pos[0] != p.pos[1]]
        spans.append((min(p[0] for p in positions), max(p[1] for p in positions)))
    window_start, window_end = spans[0][0], spans[-1][1]
    window = converted.phonemes[window_start:window_end]
    chunks = chunck_phonemes(window)
    if ''.join(chunks) != window:
        raise ValueError('Reference has unparsed sound symbols')
    boundaries, offset = {0: 0}, 0
    for idx, chunk in enumerate(chunks):
        offset += len(chunk)
        boundaries[offset] = idx+1
    start, end = (boundaries[p-window_start] for p in spans[1])
    return chunks, start, end, hashlib.sha256(window.encode()).hexdigest()


def evaluate(input_report, protocol, sura, aya, word):
    reference, start, end, ref_hash = make_reference(protocol, sura, aya, word)
    from quran_transcript.phonetics.sifa import chunck_phonemes
    expected_pins = json.loads((HERE / 'muaalem-pins.json').read_text())
    if input_report.get('pins') != expected_pins:
        raise ValueError('Use the frozen Muaalem adapter output')
    clips = input_report['clips']
    if not 1 <= len(clips) <= 10:
        raise ValueError('Invalid number of inputs')
    rows = []
    for index, clip in enumerate(clips):
        hypothesis = clip['raw_phonemes']
        if not isinstance(hypothesis, str) or len(hypothesis) > 16384:
            raise ValueError('Invalid hypothesis')
        chunks = chunck_phonemes(hypothesis)
        if ''.join(chunks) != hypothesis or set(''.join(reference)+hypothesis) - set(protocol['alphabet']):
            outcome = {'status': 'unsure', 'reason': 'unsupported_sound_symbols'}
        else:
            outcome = align_window(reference, chunks, start, end, protocol['context_budget'])
        rows.append({'index': index, **outcome})
    return {'privacy': 'PRIVATE development-case diagnostics; not verified learner errors',
            'reference': {'sura': sura, 'aya': aya, 'word': word, 'derived_window_sha256': ref_hash},
            'protocol_sha256': sha256_file(HERE / 'omission-protocol.json'),
            'implementation_sha256': {name: sha256_file(HERE / name) for name in
                ('omission_probe.py', 'muaalem.py', 'batch.py', 'benchmark.py',
                 'omission-protocol.json', 'omission-requirements-linux-cpu.lock')},
            'clips': rows,
            'limitations': ['Not held-out data or an accuracy score',
                            'No target difference does not prove correct recitation',
                            'Unsure is not an accepted control or a detected mistake']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--sura', type=int, required=True)
    parser.add_argument('--aya', type=int, required=True)
    parser.add_argument('--word', type=int, required=True)
    args = parser.parse_args()
    try:
        source, output = outside_checkout(args.input), outside_checkout(args.output)
        if source.stat().st_size > 200000 or output.exists():
            raise ValueError('Oversized input or existing output')
        protocol = json.loads((HERE / 'omission-protocol.json').read_text())
        report = evaluate(json.loads(source.read_text()), protocol, args.sura, args.aya, args.word)
        save_report(output, report)
        print('Saved private diagnostic counts. Delete after the agreed test.')
        return 0
    except Exception:
        print('Probe failed; no diagnostic saved. Check input, reference version and word scope.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
