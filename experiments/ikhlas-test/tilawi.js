import pins from './tilawi-pins.json';
export async function checkedAsset(name) {
  const pin = pins.files.find(f => f.path === name);
  if (!pin) throw new Error('Unknown asset');
  const response = await fetch(`https://huggingface.co/${pins.repo}/resolve/${pins.revision}/${name}`, { cache: 'force-cache' });
  if (!response.ok) throw new Error('Asset unavailable');
  const bytes = new Uint8Array(await response.arrayBuffer());
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
  if (bytes.length !== pin.bytes || digest !== pin.sha256) throw new Error('Asset integrity failed');
  return bytes;
}
export function decodeCTC(output, vocab) {
  const classes = output.dims.at(-1), frames = output.dims.at(-2);
  if (classes !== 1025 || !frames || output.data.length !== frames * classes) throw new Error('Invalid logits');
  let previous = -1;
  const tokens = [];
  for (let t = 0; t < frames; t++) {
    let best = 0;
    for (let k = 0; k < classes; k++) {
      const value = output.data[t * classes + k];
      if (!Number.isFinite(value)) throw new Error('Invalid logits');
      if (value > output.data[t * classes + best]) best = k;
    }
    if (best !== 1024 && best !== previous) {
      if (typeof vocab[String(best)] !== 'string') throw new Error('Unknown token');
      tokens.push(vocab[String(best)]);
    }
    previous = best;
  }
  return tokens.join('').replaceAll('▁', ' ').trim();
}
