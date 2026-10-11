import test from 'node:test';
import assert from 'node:assert/strict';
import { compareWords, normalize, selectReference } from '../word-check.js';
import { syntheticRecords } from './browser-fixtures.js';

const reference = selectReference(syntheticRecords, 112);
const text = reference.flatMap(v => v.words.map(w => w.text)).join(' ');
const fromWords = (lines) => lines.map((source, i) => ({ id: i + 1, source,
  words: source.split(' ').map((word, j) => ({ text: word, position: j + 1, forms: new Set([word]) })) }));

test('normalization preserves repeated words and never changes source strings', () => {
  const source = '  amber, amber! birch  ';
  assert.deepEqual(normalize(source), ['amber', 'amber', 'birch']);
  assert.equal(source, '  amber, amber! birch  ');
  const before = JSON.stringify(syntheticRecords);
  selectReference(syntheticRecords, 112, false);
  assert.equal(JSON.stringify(syntheticRecords), before);
});

test('opening scope changes comparison only, with source word positions retained', () => {
  const without = selectReference(syntheticRecords, 112, false);
  assert.equal(reference.length, 5);
  assert.equal(without.length, 4);
  assert.equal(reference[0].id, 'opening');
  assert.equal(without[0].source, syntheticRecords[7].text_uthmani);
  assert.equal(without[0].words[0].position, 5);
  assert.deepEqual(without[0].words.map(w => w.text), ['amber', 'birch', 'cedar']);
  assert.deepEqual(selectReference(syntheticRecords, 1, false), selectReference(syntheticRecords, 1, true));
});

test('missing, duplicated, reordered and empty source records fail closed', () => {
  for (const records of [syntheticRecords.slice(1), [...syntheticRecords, syntheticRecords[7]],
    [...syntheticRecords.slice(0, 7), syntheticRecords[8], syntheticRecords[7], ...syntheticRecords.slice(9)],
    syntheticRecords.map((r, i) => i === 8 ? { ...r, text_uthmani: ' ' } : r),
    syntheticRecords.map((r, i) => i === 7 ? { ...r, text_uthmani: 'wrong opening boundary' } : r)]) {
    assert.throws(() => selectReference(records, 112));
  }
  assert.throws(() => selectReference(syntheticRecords, 2));
});

test('an exact passage remains tentative and pronunciation is always unsure', () => {
  const result = compareWords(reference, text);
  assert.equal(result.status, 'tentative');
  assert.equal(result.pronunciation, 'unsure');
  assert.deepEqual(result.skips, []);
  assert.deepEqual(result.repeats, []);
  assert.equal(result.outsideWords, 0);
});

test('one interior omission identifies its original verse and source position', () => {
  const result = compareWords(reference, text.replace('birch ', ''));
  assert.equal(result.status, 'tentative');
  assert.deepEqual(result.skips, [{ verse: 1, position: 6 }]);
  assert.deepEqual(result.repeats, []);
  assert.equal(result.pronunciation, 'unsure');
});

test('repeated final verse remains in the hypothesis and is reported', () => {
  for (const count of [1, 2]) {
    const result = compareWords(reference, text + ' jade kite larch moss'.repeat(count));
    assert.equal(result.status, 'tentative');
    assert.deepEqual(result.repeats, Array(count).fill(4));
    assert.deepEqual(result.skips, []);
  }
});

test('short final verse repeats cannot disappear into unassessed closing words', () => {
  for (const final of ['seven eight', 'seven eight nine']) {
    const verses = fromWords(['one two three', 'four five six', final]);
    const hypothesis = verses.map(v => v.source).join(' ') + ' ' + final;
    const result = compareWords(verses, hypothesis);
    assert.equal(result.status, 'tentative');
    assert.deepEqual(result.repeats, [3]);
    assert.equal(result.outsideWords, 0);
  }
});

test('substitutions, isolated repetition and incomplete passages stay unsure', () => {
  for (const hypothesis of ['', text.replace('birch', 'unknown'), text.replace('birch', 'birch birch'),
    text.split(' ').slice(1).join(' '), text.split(' ').slice(0, -1).join(' '), 'amber birch']) {
    const result = compareWords(reference, hypothesis);
    assert.equal(result.status, 'unsure', hypothesis);
    assert.equal(result.pronunciation, 'unsure');
    assert.deepEqual(result.skips, []);
    assert.deepEqual(result.repeats, []);
  }
});

test('ambiguous omission positions do not become a confident skip', () => {
  const verses = fromWords(['start alpha alpha finish']);
  const result = compareWords(verses, 'start alpha finish');
  assert.equal(result.status, 'unsure');
  assert.deepEqual(result.skips, []);
});

test('one or two unrelated closing words are explicitly unassessed', () => {
  for (const ending of ['extra', 'extra closing']) {
    const result = compareWords(reference, text + ' ' + ending);
    assert.equal(result.status, 'tentative');
    assert.equal(result.outsideWords, ending.split(' ').length);
    assert.equal(result.pronunciation, 'unsure');
    assert.deepEqual(result.repeats, []);
  }
  assert.equal(compareWords(reference, text + ' extra closing phrase').status, 'unsure');
});

test('invalid and oversized hypotheses never yield findings', () => {
  for (const hypothesis of [null, {}, 'a'.repeat(5001), 'word '.repeat(201)]) {
    const result = compareWords(reference, hypothesis);
    assert.equal(result.status, 'unsure');
    assert.deepEqual(result.skips, []);
    assert.deepEqual(result.repeats, []);
  }
});
