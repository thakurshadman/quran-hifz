// These doubles test lifecycle contracts, not microphone hardware or ASR quality.
export async function installDoubles(page) {
  await page.addInitScript(() => {
    const state = window.testDevices = {
      permission: 'allow', requests: 0, streams: [], contexts: [], workers: [],
      autoReady: true, resolvePermission: null,
    };
    function stream() {
      const track = new EventTarget();
      track.stopped = false;
      track.stop = () => { track.stopped = true; };
      track.readyState = 'live';
      const value = { getTracks: () => [track], getAudioTracks: () => [track] };
      state.streams.push(value);
      return value;
    }
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
      configurable: true,
      value: async () => {
        state.requests++;
        if (state.permission === 'deny') throw new DOMException('Denied', 'NotAllowedError');
        if (state.permission === 'pending') {
          return new Promise((resolve) => { state.resolvePermission = () => resolve(stream()); });
        }
        return stream();
      },
    });
    class Node {
      connect() {}
      disconnect() { this.disconnected = true; }
    }
    class Context {
      constructor() {
        this.sampleRate = 48_000;
        this.state = 'running';
        this.destination = new Node();
        this.audioWorklet = { addModule: async () => {} };
        state.contexts.push(this);
      }
      async resume() { this.state = 'running'; }
      async close() { this.state = 'closed'; }
      createMediaStreamSource() { return new Node(); }
      createGain() { return Object.assign(new Node(), { gain: { value: 1 } }); }
      createScriptProcessor() { this.processor = new Node(); return this.processor; }
    }
    window.AudioContext = Context;
    window.webkitAudioContext = Context;
    window.AudioWorkletNode = class extends Node {
      constructor(context) {
        super();
        this.port = { postMessage() {}, close() {}, onmessage: null };
        context.processor = this;
      }
    };
    window.Worker = class extends EventTarget {
      constructor() {
        super();
        this.messages = [];
        this.terminated = false;
        state.workers.push(this);
      }
      postMessage(message) {
        this.messages.push(message);
        if (message.type === 'load' && state.autoReady) {
          queueMicrotask(() => this.emit({ type: 'ready' }));
        }
      }
      terminate() { this.terminated = true; }
      emit(data) {
        const event = new MessageEvent('message', { data });
        this.dispatchEvent(event);
        this.onmessage?.(event);
      }
    };
    state.pushSamples = (length = 4800, value = 0.1) => {
      const processor = state.contexts.at(-1)?.processor;
      const samples = new Float32Array(length).fill(value);
      if (processor?.onaudioprocess) {
        processor.onaudioprocess({ inputBuffer: { getChannelData: () => samples } });
      } else if (processor?.port?.onmessage) {
        processor.port.onmessage({ data: { type: 'audio', audio: samples } });
      } else {
        throw new Error('Capture has no active sample callback');
      }
    };
    state.loseDevice = () => {
      const track = state.streams.at(-1).getTracks()[0];
      track.readyState = 'ended';
      track.dispatchEvent(new Event('ended'));
      track.onended?.(new Event('ended'));
    };
    state.interruptContext = (reason) => {
      const context = state.contexts.at(-1);
      context.state = reason;
      context.onstatechange?.(new Event('statechange'));
    };
  });
}

export async function expectResourcesReleased(page, expect) {
  await expect.poll(() => page.evaluate(() => window.testDevices.streams.every(
    (stream) => stream.getTracks().every((track) => track.stopped),
  ))).toBe(true);
  await expect.poll(() => page.evaluate(() => window.testDevices.contexts.every(
    (context) => context.state === 'closed',
  ))).toBe(true);
}
