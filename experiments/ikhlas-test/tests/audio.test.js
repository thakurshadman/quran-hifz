import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { resample, MAX_SECONDS, TARGET_RATE } from '../capture.js';

test('48 kHz capture becomes 16 kHz without changing duration or mutating the input', () => {
  const input = new Float32Array(48_000).fill(0.25);
  const output = resample(input, 48_000);
  assert.equal(output.length, 16_000);
  assert.ok(output.every((value) => value === 0.25));
  assert.ok(input.every((value) => value === 0.25));
});

test('44.1 kHz resampling preserves a low-frequency signal within declared tolerance', () => {
  const input = Float32Array.from({ length: 44_100 }, (_, i) => Math.sin(2 * Math.PI * 220 * i / 44_100));
  const output = resample(input, 44_100);
  assert.equal(output.length, 16_000);
  let squaredError = 0;
  for (let i = 0; i < output.length; i++) squaredError += (output[i] - Math.sin(2 * Math.PI * 220 * i / 16_000)) ** 2;
  assert.ok(Math.sqrt(squaredError / output.length) < 0.001);
});

test('resampler bounds duration and handles empty and invalid input', () => {
  assert.equal(resample(new Float32Array(48_000 * 31), 48_000).length, MAX_SECONDS * TARGET_RATE);
  assert.equal(resample(new Float32Array(), 48_000).length, 0);
  for (const rate of [0, -1, NaN, Infinity]) assert.throws(() => resample(new Float32Array(1), rate), TypeError);
  assert.throws(() => resample([1], 48_000), TypeError);
});

test('audio worklet emits no more than thirty seconds and ends exactly once', () => {
  let Processor;
  const messages = [];
  const sandbox = {
    sampleRate: 48_000,
    Float32Array,
    AudioWorkletProcessor: class { constructor() { this.port = { postMessage: (message) => messages.push(message) }; } },
    registerProcessor: (name, type) => { assert.equal(name, 'microphone-capture'); Processor = type; },
  };
  vm.runInNewContext(fs.readFileSync(new URL('../capture-worklet.js', import.meta.url), 'utf8'), sandbox);
  const processor = new Processor();
  const input = new Float32Array(128).fill(0.25);
  assert.equal(processor.process([]), true);
  for (let i = 0; i < (48_000 * 31) / input.length; i++) processor.process([[input]]);
  const audio = messages.filter((message) => message.type === 'audio');
  assert.equal(audio.reduce((sum, message) => sum + message.audio.length, 0), 48_000 * 30);
  assert.ok(audio.every((message) => message.audio.every((value) => value === 0.25)));
  assert.equal(messages.filter((message) => message.type === 'limit').length, 1);
  assert.equal(processor.process([[input]]), false);
});
