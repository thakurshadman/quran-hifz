// Browser/native bridge only. All normalization, selection and comparison run in Rust.
import init, { normalize_json, select_reference_json, passage_json, choose_json, compare_json } from './rust-pkg/hifz_core.js';
const wasmUrl = new URL('./rust-pkg/hifz_core_bg.wasm', import.meta.url);
export let coreError = null;
try {
if (typeof process !== 'undefined' && process.versions?.node) {
  const moduleName = 'node:fs/promises';
  const { readFile } = await import(/* @vite-ignore */ moduleName);
  await init({ module_or_path: await readFile(wasmUrl) });
} else {
  const controller = new AbortController();
  const deadline = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(wasmUrl, { signal: controller.signal });
    if (!response.ok) throw new Error('Engine unavailable');
    const bytes = await response.arrayBuffer();
    await init({ module_or_path: bytes });
  } finally { clearTimeout(deadline); }
}
} catch { coreError = 'The practice engine could not load. Reload the page to try again.'; }
const unpack = data => JSON.parse(data).map(v => ({ ...v, words: v.words.map(w => ({ ...w, forms: new Set(w.forms) })) }));
export const normalize = text => JSON.parse(normalize_json(text));
export const selectReference = (records, surah, basmala = true) => unpack(select_reference_json(JSON.stringify(records), surah, basmala));
export const selectPassage = (records, surah, first, last, basmala = true) => unpack(passage_json(JSON.stringify(records), surah, first, last, basmala));
export const choosePassage = (records, scope, seed, length) => JSON.parse(choose_json(JSON.stringify(records), JSON.stringify(scope), seed, length));
export function compareWords(verses, text) {
  if (typeof text !== 'string' || text.length > 5000) return { status:'unsure', reason:'invalid', skips:[], repeats:[], pronunciation:'unsure' };
  return JSON.parse(compare_json(JSON.stringify(verses, (_key,value) => value instanceof Set ? [...value] : value), text));
}
