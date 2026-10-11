// Only public source metadata is printed. Never pass private recordings here.
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { selectReference, selectPassage } from '../word-check.js';
const path = process.argv[2];
if (!path) throw new Error('Pass the downloaded public quran.json path');
const pins = JSON.parse(await readFile(new URL('../tilawi-pins.json', import.meta.url)));
const pin = pins.files.find(f => f.path === 'quran.json');
const bytes = await readFile(path);
if (bytes.length !== pin.bytes || createHash('sha256').update(bytes).digest('hex') !== pin.sha256) throw new Error('Reference checksum mismatch');
const records = JSON.parse(bytes);
let checked = 0;
for (const surah of [1,112,...Array.from({length:11},(_,i)=>i+67)]) {
  const verses = selectReference(records,surah,false);
  for (const verse of verses) {
    if (typeof verse.id !== 'number') continue;
    const source = records.find(r=>r.surah===surah && r.ayah===verse.id);
    if (source.text_uthmani !== verse.source) throw new Error('Source changed');
    selectPassage(records,surah,verse.id,verse.id,false);
    checked++;
  }
}
console.log(JSON.stringify({sourceChecksum:'pass',sourceVerses:checked,displayPreserved:true,qualifiedContentReview:false}));
