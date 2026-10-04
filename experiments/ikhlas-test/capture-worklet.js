// Only microphone samples cross this port; there is no network or persistence.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.remaining = Math.floor(sampleRate * 30);
    this.buffer = new Float32Array(1024);
    this.used = 0;
    this.active = true;
  }

  flush() {
    if (!this.used) return;
    const audio = this.buffer.slice(0, this.used);
    this.port.postMessage({ type: 'audio', audio }, [audio.buffer]);
    this.buffer.fill(0);
    this.used = 0;
  }

  process(inputs) {
    if (!this.active) return false;
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (let i = 0; i < channel.length && this.remaining > 0; i++) {
      this.buffer[this.used++] = channel[i];
      this.remaining--;
      if (this.used === this.buffer.length) this.flush();
    }
    if (this.remaining === 0) {
      this.flush();
      this.active = false;
      this.port.postMessage({ type: 'limit' });
    }
    return this.active;
  }
}

registerProcessor('microphone-capture', CaptureProcessor);
