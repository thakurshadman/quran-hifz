import { coreError, selectReference, selectPassage, choosePassage, compareWords } from './word-check.js';
import { MicrophoneCapture, microphoneError, MAX_SECONDS } from './capture.js';

const ui = Object.fromEntries(['load', 'start', 'stop', 'cancel', 'clear', 'status', 'level', 'timer',
  'mic-label', 'state-badge', 'result-panel', 'transcript', 'timing', 'surah', 'basmala', 'word-summary', 'word-findings', 'reference-verses', 'verse-first', 'verse-last', 'random', 'scope', 'practice-length', 'passage-label', 'reveal', 'cue', 'cue-text', 'next-practice', 'session-count'].map((id) => [id, document.getElementById(id)]));
let state = 'idle';
let records = null;
let activeReference = null;
let worker = null;
let operation = 0;
let interval = null;
let timeout = null;
let startedAt = 0;
let attempts = 0;
const counts = {1:7,112:4,67:30,68:52,69:52,70:44,71:28,72:28,73:20,74:56,75:40,76:31,77:50};
const labels = { idle: 'Not loaded', loading: 'Loading', ready: 'Ready', requesting: 'Allow microphone',
  recording: 'Listening', transcribing: 'Working', result: 'Complete' };

function display(next, message) {
  state = next;
  ui.status.textContent = message;
  ui['state-badge'].textContent = labels[next];
  ui.load.hidden = next !== 'idle';
  ui.start.hidden = !['ready', 'result'].includes(next);
  ui.start.textContent = next === 'result' ? 'Try again' : 'Start reciting';
  ui.stop.hidden = next !== 'recording';
  ui.cancel.hidden = !['loading', 'requesting', 'recording', 'transcribing'].includes(next);
  ui.clear.hidden = next !== 'result';
  ui.random.disabled = ui.reveal.disabled = !records || !['ready', 'result'].includes(next);
  if (['requesting', 'recording', 'transcribing'].includes(next)) hideCue();
  ui['mic-label'].textContent = next === 'recording' ? 'Microphone on'
    : next === 'requesting' ? 'Starting microphone…' : 'Microphone off';
}

function clearResult() {
  ui.transcript.textContent = '';
  ui.timing.textContent = '';
  ui['result-panel'].hidden = true;
  ui['word-summary'].textContent = '';
  ui['word-findings'].replaceChildren();
  ui['reference-verses'].replaceChildren();
  hideCue();
}

function clearTimers() {
  clearInterval(interval);
  clearTimeout(timeout);
  interval = timeout = null;
}

const capture = new MicrophoneCapture({
  onLevel: (level) => { ui.level.value = level; },
  onLimit: () => finish(),
  onError: (message) => {
    operation++;
    clearTimers();
    clearResult();
    display(worker ? 'ready' : 'idle', message);
  },
});

function reset(message = 'Test cleared. Load the model when you are ready.') {
  operation++;
  clearTimers();
  capture.cancel();
  worker?.terminate();
  worker = null;
  records = activeReference = null;
  clearResult();
  ui.timer.textContent = '0:00 / 1:00';
  display('idle', message);
}

ui.load.addEventListener('click', () => {
  if (state !== 'idle') return;
  const id = ++operation;
  display('loading', 'Downloading the speech model. This may take a minute. The microphone is off.');
  try {
    const current = new Worker(new URL('./recognizer-worker.js', import.meta.url), { type: 'module' });
    worker = current;
    current.onmessage = ({ data }) => {
      if (worker !== current) return;
      if (data.type === 'progress' && state === 'loading') {
        ui.status.textContent = typeof data.message === 'string' ? data.message.slice(0, 240) : 'Loading the speech model…';
      } else if (data.type === 'ready' && state === 'loading' && operation === id) {
        clearTimers();
        try {
          selectReference(data.records, 1); selectReference(data.records, 112);
          records = data.records;
        } catch { reset('The reference could not be verified. Reload before trying again.'); return; }
        display('ready', 'Ready. Choose your passage, press Start and recite from memory, then press Stop.');
      } else if (data.type === 'result' && state === 'transcribing') {
        clearTimers();
        if (typeof data.text !== 'string' || data.text.length > 5000) { reset('The recognised text was invalid or too long. No word judgement was made.'); return; }
        const text = data.text.trim();
        if (!text) {
          display('ready', 'No words were recognized. That is not a judgement of your recitation. Try again closer to your microphone.');
          return;
        }
        ui.transcript.textContent = text;
        showWordCheck(text);
        ui['session-count'].textContent = String(++attempts);
        ui.timing.textContent = Number.isFinite(data.elapsedMs) && data.elapsedMs >= 0
          ? `Processing took ${(data.elapsedMs / 1000).toFixed(1)} seconds on this device.` : '';
        ui['result-panel'].hidden = false;
        display('result', 'Done. The text below is the AI’s guess. It may miss words or invent them.');
      } else if (data.type === 'error') {
        reset('The speech model could not finish. Check your connection and available memory, then load it again.');
      }
    };
    current.onerror = (event) => {
      event.preventDefault();
      if (worker === current) reset('The speech model could not run in this browser. Try a recent browser or another device.');
    };
    current.postMessage({ type: 'load' });
    timeout = setTimeout(() => {
      if (worker === current && state === 'loading') reset('The model took too long to load. Check your connection and try again.');
    }, 180000);
  } catch {
    reset('This browser could not start the speech test. Try a recent browser.');
  }
});

ui.start.addEventListener('click', async () => {
  if (!['ready', 'result'].includes(state)) return;
  const id = ++operation;
  clearResult();
  try { activeReference = selectedPassage(); }
  catch { display('ready', 'Choose a valid verse range with no more than 100 words.'); return; }
  ui.timer.textContent = '0:00 / 1:00';
  display('requesting', 'Allow microphone access when your browser asks. You can cancel at any time.');
  try {
    const active = await capture.start();
    if (!active || id !== operation) return;
    startedAt = performance.now();
    display('recording', 'Listening. Recite your selected passage, then press Stop. Capture ends after 60 seconds.');
    interval = setInterval(() => {
      const seconds = Math.min(MAX_SECONDS, Math.floor((performance.now() - startedAt) / 1000));
      ui.timer.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} / 1:00`;
    }, 200);
    timeout = setTimeout(finish, MAX_SECONDS * 1000);
  } catch (error) {
    if (id !== operation) return;
    const message = error?.name === 'Error' ? error.message : microphoneError(error);
    display('ready', message);
  }
});

function finish() {
  if (state !== 'recording') return;
  clearTimers();
  const audio = capture.stop();
  if (audio.length < 1600) {
    audio.fill(0);
    display('ready', 'That was too short to hear. Press Start and try again.');
    return;
  }
  display('transcribing', 'Microphone off. The AI is processing on your device. This may take a while.');
  try {
    worker.postMessage({ type: 'transcribe', audio }, [audio.buffer]);
    timeout = setTimeout(() => {
      if (state === 'transcribing') reset('Processing took too long on this device. Try a shorter recitation or a faster device.');
    }, 180000);
  } catch {
    if (audio.byteLength) audio.fill(0);
    reset('The speech test stopped unexpectedly. Load it again to retry.');
  }
}

ui.stop.addEventListener('click', finish);
ui.cancel.addEventListener('click', () => {
  if (['loading', 'transcribing'].includes(state)) {
    reset('Cancelled. Audio and results cleared. Load the model to try again.');
  } else {
    operation++;
    clearTimers();
    capture.cancel();
    clearResult();
    ui.timer.textContent = '0:00 / 1:00';
    display('ready', 'Cancelled. Microphone off and audio cleared. Try again when ready.');
  }
});
ui.clear.addEventListener('click', () => {
  clearResult();
  ui.timer.textContent = '0:00 / 1:00';
  display('ready', 'Result cleared. Press Start for another try.');
});
window.addEventListener('pagehide', () => reset());
document.addEventListener('visibilitychange', () => {
  if (document.hidden) reset('Test paused and cleared when you left this tab. Load it again when ready.');
});

function showWordCheck(text) {
  const result = compareWords(activeReference, text);
  ui['word-summary'].textContent = result.status === 'unsure'
    ? 'Word check: unsure. The recognised words do not give a clear match.'
    : result.skips.length || result.repeats.length
      ? 'Possible skips or repeats in the recognised words. Check these yourself.'
      : 'No clear whole-word skips or verse repeats found. This does not prove correct recitation.';
  function item(message) { const li = document.createElement('li'); li.textContent = message; ui['word-findings'].append(li); }
  for (const skip of result.skips) item(`Possible skip: ${skip.verse === 'opening' ? 'opening' : `verse ${skip.verse}`}, source word ${skip.position}.`);
  for (const verse of result.repeats) item(`Possible repeat: ${verse === 'opening' ? 'opening' : `verse ${verse}`}.`);
  if (result.outsideWords) item('Closing words: unsure; not checked.');
  for (const verse of activeReference.filter(v => v.id !== 'opening')) {
    const p = document.createElement('p'); p.lang = 'ar'; p.dir = 'rtl'; p.textContent = verse.source;
    ui['reference-verses'].append(p);
  }
}
function changePassage() {
  updatePassageLabel();
  ui.basmala.disabled = ui.surah.value === '1';
  if (['loading', 'requesting', 'recording', 'transcribing'].includes(state)) reset('Passage changed. Attempt cleared; reload the test.');
  else { clearResult(); activeReference = null; if (state === 'result') display('ready', 'Passage changed. Start a new attempt.'); }
}
ui.surah.addEventListener('change', () => {
  const count = counts[ui.surah.value];
  ui['verse-first'].value = '1'; ui['verse-last'].value = String(['1','112'].includes(ui.surah.value) ? count : Math.min(3,count));
  ui['verse-first'].max = ui['verse-last'].max = String(count);
  changePassage();
});
ui.basmala.addEventListener('change', changePassage);

function selectedPassage() {
  const first = Number(ui['verse-first'].value), last = Number(ui['verse-last'].value);
  if (!Number.isInteger(first) || !Number.isInteger(last) || first < 1 || last < first || last > counts[ui.surah.value]) throw new Error('Invalid range');
  return selectPassage(records, Number(ui.surah.value), first, last, ui.basmala.checked);
}
function hideCue() { ui.cue.hidden = true; ui['cue-text'].textContent = ''; ui.reveal.textContent = 'Show first verse'; }
function updatePassageLabel() {
  const name = ui.surah.selectedOptions[0]?.textContent || 'Passage';
  ui['passage-label'].textContent = `${name} · verses ${ui['verse-first'].value}–${ui['verse-last'].value}`;
}
for (const id of ['verse-first','verse-last']) ui[id].addEventListener('change', changePassage);
function randomPassage() {
  if (!records || !['ready','result'].includes(state)) return;
  try {
    const scope = ui.scope.value === 'juz29' ? Array.from({length:11},(_,i)=>i+67) : [Number(ui.surah.value)];
    const seed = crypto.getRandomValues(new Uint32Array(1))[0];
    const choice = choosePassage(records, scope, seed, Number(ui['practice-length'].value));
    ui.surah.value = String(choice.surah);
    ui['verse-first'].max = ui['verse-last'].max = String(counts[choice.surah]);
    ui['verse-first'].value = String(choice.first); ui['verse-last'].value = String(choice.last);
    // Random ranges omit the opening except in Al-Fatiha, where verse 1 is the opening.
    ui.basmala.checked = false;
    changePassage();
    display('ready','Your next passage is ready. Show the first verse if you need a cue, then start.');
  } catch { display('ready','This passage could not be prepared. Choose a shorter range or reload.'); }
}
ui.random.addEventListener('click',randomPassage);
ui['next-practice'].addEventListener('click',randomPassage);
ui.reveal.addEventListener('click',() => {
  if (!ui.cue.hidden) {hideCue(); return;}
  try {
    const first = selectedPassage().find(v=>v.id !== 'opening');
    ui['cue-text'].textContent = first.source; ui.cue.hidden = false; ui.reveal.textContent = 'Hide verse';
  } catch { ui.status.textContent='Choose a valid range of up to 100 words first.'; }
});

const reloadApp = document.getElementById('reload-app');
if (coreError) {
  display('idle', coreError);
  ui.load.disabled = true;
  reloadApp.hidden = false;
} else {
  ui.load.disabled = false;
  display('idle', 'Load the speech model to begin. Your microphone stays off until you press Start.');
}
