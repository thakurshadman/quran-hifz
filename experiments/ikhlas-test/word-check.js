// Comparison copies only. Source Uthmani strings are never changed for display.
export function normalize(text) {
  return text.normalize('NFC').replace(/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]/gu, '')
    .replace(/[\p{M}ـ]/gu, '').replace(/[أإآٱ]/gu, 'ا').replace(/[^\p{L}\p{N}\s]/gu, ' ').trim().split(/\s+/u).filter(Boolean);
}
function wordForms(text) {
  return new Set([...normalize(text), ...normalize(text.replaceAll('\u0670', 'ا'))]);
}
export function selectReference(records, surah, basmala = true) {
  if (![1, 112].includes(surah) || !Array.isArray(records)) throw new Error('Unsupported passage');
  const count = surah === 1 ? 7 : 4;
  const rows = records.filter(r => r.surah === surah);
  if (rows.length !== count || rows.some((r, i) => r.ayah !== i + 1 || typeof r.text_uthmani !== 'string' || !r.text_uthmani.trim())) throw new Error('Invalid reference');
  const opening = records.filter(r => r.surah === 1 && r.ayah === 1);
  if (opening.length !== 1) throw new Error('Invalid opening');
  const prefix = normalize(opening[0].text_uthmani);
  const verses = rows.map(r => ({ id: r.ayah, source: r.text_uthmani, words: r.text_uthmani.trim().split(/\s+/u).map((text, i) => ({ text, position: i + 1, forms: wordForms(text) })) }));
  if (surah === 112) {
    if (prefix.length !== 4 || !prefix.every((w, i) => verses[0].words[i]?.forms.has(w))) throw new Error('Unexpected opening boundary');
    const openingWords = verses[0].words.slice(0, 4);
    verses[0].words = verses[0].words.slice(4);
    if (basmala) verses.unshift({ id: 'opening', source: opening[0].text_uthmani, words: openingWords });
  }
  if (verses.some(v => !v.words.length || v.words.some(w => !w.forms.size))) throw new Error('Empty reference');
  return verses;
}

export function compareWords(verses, text) {
  const unsure = reason => ({ status: 'unsure', reason, skips: [], repeats: [], pronunciation: 'unsure' });
  if (typeof text !== 'string' || text.length > 5000) return unsure('invalid');
  const hypothesis = normalize(text);
  const reference = verses.flatMap(v => v.words.map(w => ({ ...w, verse: v.id })));
  const n = reference.length, m = hypothesis.length;
  if (!n || n > 100 || !m || m > 200) return unsure('not_enough_words');
  const endings = new Map();
  let end = 0;
  for (const verse of verses) { end += verse.words.length; endings.set(end, verse); }
  const cells = Array.from({ length: n + 1 }, () => Array.from({ length: m + 1 }, () => ({ cost: Infinity, ways: 0, previous: null })));
  // At most two closing words are left explicitly unassessed, never called correct.
  cells[0][0] = { cost: 0, ways: 1, previous: null };
  function move(i, j, ni, nj, extra, op) {
    const value = cells[i][j].cost + extra, to = cells[ni][nj];
    if (value < to.cost) { to.cost = value; to.ways = cells[i][j].ways; to.previous = [i, j, op]; }
    else if (value === to.cost) to.ways = Math.min(2, to.ways + cells[i][j].ways);
  }
  for (let i = 0; i <= n; i++) for (let j = 0; j <= m; j++) {
    if (!cells[i][j].ways) continue;
    if (i < n) move(i, j, i + 1, j, 1, 'skip');
    if (i > 0 && j < m) move(i, j, i, j + 1, 1, 'extra');
    if (i < n && j < m) move(i, j, i + 1, j + 1, reference[i].forms.has(hypothesis[j]) ? 0 : 1,
      reference[i].forms.has(hypothesis[j]) ? 'match' : 'different');
    const verse = endings.get(i);
    if (verse && j + verse.words.length <= m && verse.words.every((w, k) => w.forms.has(hypothesis[j + k]))) {
      move(i, j, i, j + verse.words.length, 1, 'repeat');
    }
  }
  const candidates = cells[n].flatMap((c, j) => j >= m - 2 && hypothesis.slice(j).every(word => reference.every(r => !r.forms.has(word))) ? [j] : []);
  const best = Math.min(...candidates.map(j => cells[n][j].cost));
  const ends = candidates.filter(j => cells[n][j].cost === best);
  if (ends.reduce((sum, j) => sum + cells[n][j].ways, 0) !== 1) return unsure('ambiguous');
  let i = n, j = ends[0];
  const steps = [];
  while (i) {
    const [pi, pj, op] = cells[i][j].previous;
    steps.push({ op, index: pi, verse: endings.get(pi)?.id }); i = pi; j = pj;
  }
  steps.reverse();
  const matched = steps.filter(s => s.op === 'match').length;
  if (matched / n < 0.7 || steps.some(s => ['different', 'extra'].includes(s.op))) return unsure('unclear_words');
  if (steps[0]?.op === 'skip' || steps.at(-1)?.op === 'skip') return unsure('incomplete_passage');
  return { status: 'tentative', pronunciation: 'unsure',
    outsideWords: j + m - ends[0],
    skips: steps.filter(s => s.op === 'skip').map(s => ({ verse: reference[s.index].verse, position: reference[s.index].position })),
    repeats: steps.filter(s => s.op === 'repeat').map(s => s.verse) };
}
