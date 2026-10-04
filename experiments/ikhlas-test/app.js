import { MicrophoneCapture, microphoneError, MAX_SECONDS } from './capture.js';

const ui = Object.fromEntries(['load', 'start', 'stop', 'cancel', 'clear', 'status', 'level', 'timer',
  'mic-label', 'state-badge', 'result-panel', 'transcript', 'timing'].map((id) => [id, document.getElementById(id)]));
let state = 'idle';
let worker = null;
let operation = 0;
let interval = null;
let timeout = null;
let startedAt = 0;
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
  ui['mic-label'].textContent = next === 'recording' ? 'Microphone on'
    : next === 'requesting' ? 'Starting microphone…' : 'Microphone off';
}

function clearResult() {
  ui.transcript.textContent = '';
  ui.timing.textContent = '';
  ui['result-panel'].hidden = true;
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
  clearResult();
  ui.timer.textContent = '0:00 / 0:30';
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
        display('ready', 'Ready. Press Start and recite Al-Ikhlas from memory, then press Stop.');
      } else if (data.type === 'result' && state === 'transcribing') {
        clearTimers();
        const text = typeof data.text === 'string' ? data.text.trim().slice(0, 5000) : '';
        if (!text) {
          display('ready', 'No words were recognized. That is not a judgement of your recitation. Try again closer to your microphone.');
          return;
        }
        ui.transcript.textContent = text;
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
  ui.timer.textContent = '0:00 / 0:30';
  display('requesting', 'Allow microphone access when your browser asks. You can cancel at any time.');
  try {
    const active = await capture.start();
    if (!active || id !== operation) return;
    startedAt = performance.now();
    display('recording', 'Listening. Recite Al-Ikhlas, then press Stop. Capture ends after 30 seconds.');
    interval = setInterval(() => {
      const seconds = Math.min(MAX_SECONDS, Math.floor((performance.now() - startedAt) / 1000));
      ui.timer.textContent = `0:${String(seconds).padStart(2, '0')} / 0:30`;
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
    ui.timer.textContent = '0:00 / 0:30';
    display('ready', 'Cancelled. Microphone off and audio cleared. Try again when ready.');
  }
});
ui.clear.addEventListener('click', () => {
  clearResult();
  ui.timer.textContent = '0:00 / 0:30';
  display('ready', 'Result cleared. Press Start for another try.');
});
window.addEventListener('pagehide', () => reset());
document.addEventListener('visibilitychange', () => {
  if (document.hidden) reset('Test paused and cleared when you left this tab. Load it again when ready.');
});
