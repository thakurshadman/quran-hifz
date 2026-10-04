export const MAX_SECONDS = 30;
export const TARGET_RATE = 16000;

/** Resampling affects only temporary microphone data, never reference text. */
export function resample(audio, sourceRate, targetRate = TARGET_RATE) {
  if (!(audio instanceof Float32Array) || !Number.isFinite(sourceRate) || sourceRate <= 0 ||
      !Number.isFinite(targetRate) || targetRate <= 0) {
    throw new TypeError('Invalid audio or sample rate');
  }
  const length = Math.min(Math.floor(audio.length * targetRate / sourceRate), MAX_SECONDS * targetRate);
  const result = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const position = i * sourceRate / targetRate;
    const left = Math.floor(position);
    const fraction = position - left;
    const a = audio[left];
    const b = audio[Math.min(left + 1, audio.length - 1)];
    result[i] = a + (b - a) * fraction;
  }
  return result;
}

export function microphoneError(error) {
  switch (error?.name) {
    case 'NotAllowedError': return 'Microphone access was denied. Allow it in your browser settings, then try again.';
    case 'NotFoundError': return 'No microphone was found. Connect one and try again.';
    case 'NotReadableError': return 'The microphone is busy or unavailable. Close other apps using it and try again.';
    default: return 'The microphone could not start. Check your browser and microphone, then try again.';
  }
}

export class MicrophoneCapture {
  constructor({ onLevel = () => {}, onLimit = () => {}, onError = () => {} } = {}) {
    this.onLevel = onLevel;
    this.onLimit = onLimit;
    this.onError = onError;
    this.generation = 0;
    this.chunks = [];
    this.samples = 0;
  }

  async start() {
    this.cancel();
    const generation = this.generation;
    const AudioContextClass = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!globalThis.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      throw new Error('Open this page over HTTPS (or localhost) in a browser with microphone support.');
    }
    if (!AudioContextClass || !globalThis.AudioWorkletNode) {
      throw new Error('This browser cannot run the microphone test. Try a recent Safari, Chrome, Firefox or Edge.');
    }
    const context = new AudioContextClass();
    this.context = context;
    // Resume while still inside the button gesture, particularly on iOS.
    const resumed = context.resume();
    resumed.catch(() => {});
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
        video: false,
      });
      if (generation !== this.generation) {
        stream.getTracks().forEach((track) => track.stop());
        return false;
      }
      this.stream = stream;
      for (const track of stream.getTracks()) {
        track.onended = () => {
          if (generation !== this.generation) return;
          this.cancel();
          this.onError('The microphone disconnected. Reconnect it and try again.');
        };
      }
      await resumed;
      await context.audioWorklet.addModule(new URL('./capture-worklet.js', import.meta.url));
      if (generation !== this.generation) return false;
      if (context.state !== 'running') throw new Error('The microphone was interrupted. Tap Start again.');
      this.sampleRate = context.sampleRate;
      this.source = context.createMediaStreamSource(stream);
      this.node = new AudioWorkletNode(context, 'microphone-capture');
      this.mute = context.createGain();
      this.mute.gain.value = 0;
      this.node.port.onmessage = ({ data }) => {
        if (generation !== this.generation) return;
        if (data.type === 'audio' && data.audio instanceof Float32Array) {
          const available = Math.max(0, Math.floor(this.sampleRate * MAX_SECONDS) - this.samples);
          const chunk = data.audio.length > available ? data.audio.slice(0, available) : data.audio;
          if (chunk.length) {
            this.chunks.push(chunk);
            this.samples += chunk.length;
            let sum = 0;
            for (const value of chunk) sum += value * value;
            this.onLevel(Math.min(1, Math.sqrt(sum / chunk.length) * 5));
          }
        } else if (data.type === 'limit') {
          this.onLimit();
        }
      };
      this.node.onprocessorerror = () => {
        if (generation !== this.generation) return;
        this.cancel();
        this.onError('Audio capture stopped unexpectedly. Please try again.');
      };
      this.source.connect(this.node);
      this.node.connect(this.mute);
      this.mute.connect(context.destination);
      context.onstatechange = () => {
        if (generation !== this.generation || context.state === 'running') return;
        this.cancel();
        this.onError('The microphone was interrupted. Press Start to try again.');
      };
      return true;
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      if (generation !== this.generation) return false;
      this.cancel();
      throw error;
    }
  }

  release() {
    this.generation++;
    if (this.node) {
      this.node.port.onmessage = null;
      this.node.onprocessorerror = null;
      this.node.port.close();
      this.node.disconnect();
    }
    this.source?.disconnect();
    this.mute?.disconnect();
    this.stream?.getTracks().forEach((track) => { track.onended = null; track.stop(); });
    if (this.context) this.context.onstatechange = null;
    this.context?.close().catch(() => {});
    this.node = this.source = this.mute = this.stream = this.context = null;
    this.onLevel(0);
  }

  stop() {
    // End microphone access before allocating/resampling and running inference.
    this.release();
    const raw = new Float32Array(this.samples);
    let offset = 0;
    for (const chunk of this.chunks) {
      raw.set(chunk, offset);
      offset += chunk.length;
      chunk.fill(0);
    }
    this.chunks = [];
    this.samples = 0;
    try { return resample(raw, this.sampleRate || TARGET_RATE); }
    finally { raw.fill(0); }
  }

  cancel() {
    this.release();
    for (const chunk of this.chunks) chunk.fill(0);
    this.chunks = [];
    this.samples = 0;
  }
}
