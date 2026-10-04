// Private worker protocol: JSON on stdin, transcript only on captured stdout.
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

async function main() {
  const config = JSON.parse(readFileSync(0, 'utf8'));
  const pcm = readFileSync(config.pcm);
  const audio = new Float32Array(pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength));
  let infer, release, decoding, started, timer_scope;
  if (config.model === 'tilawi') {
    const ort = await import('../../experiments/ikhlas-test/node_modules/onnxruntime-node/dist/index.js');
    const vocab = JSON.parse(readFileSync(`${config.directory}/vocab.json`, 'utf8'));
    started = performance.now();
    const session = await ort.InferenceSession.create(`${config.directory}/fastconformer_full_mixed.onnx`, {
      executionProviders: ['cpu'], intraOpNumThreads: 2, interOpNumThreads: 1, logSeverityLevel: 3,
    });
    infer = async () => {
      const began = performance.now();
      const result = await session.run({
        audio_signal: new ort.Tensor('float32', audio, [1, audio.length]),
        length: new ort.Tensor('int64', BigInt64Array.from([BigInt(audio.length)]), [1]),
      });
      const seconds = (performance.now() - began) / 1000;
      const output = result[session.outputNames[0]];
      const classes = output.dims.at(-1), frames = output.dims.at(-2);
      if (classes !== 1025) throw new Error('Unexpected CTC shape');
      let previous = -1;
      const tokens = [];
      for (let t = 0; t < frames; t++) {
        let best = 0;
        for (let k = 1; k < classes; k++) {
          if (output.data[t * classes + k] > output.data[t * classes + best]) best = k;
        }
        if (best !== 1024 && best !== previous) tokens.push(best);
        previous = best;
      }
      const text = tokens.map(id => {
        const token = vocab[String(id)];
        if (typeof token !== 'string') throw new Error('Invalid token');
        return token;
      }).join('').replaceAll('▁', ' ').trim();
      return { text, seconds };
    };
    release = () => session.release();
    decoding = 'greedy CTC; blank 1024; no reference prompt or matcher';
    timer_scope = 'ONNX session.run only; excludes CTC collapse and text decoding';
  } else if (config.model === 'tiny') {
    const { env, pipeline } = await import('../../experiments/ikhlas-test/node_modules/@huggingface/transformers/dist/transformers.node.mjs');
    env.allowRemoteModels = false;
    env.allowLocalModels = true;
    env.useFSCache = false;
    started = performance.now();
    const model = await pipeline('automatic-speech-recognition', `${config.directory}/`, {
      dtype: 'q8', device: 'cpu',
      session_options: { intraOpNumThreads: 2, interOpNumThreads: 1, logSeverityLevel: 3 },
    });
    infer = async () => {
      const began = performance.now();
      const output = await model(audio, {
        language: 'arabic', task: 'transcribe', max_new_tokens: 128,
        return_timestamps: false, do_sample: false, num_beams: 1,
      });
      return { text: output.text, seconds: (performance.now() - began) / 1000 };
    };
    release = () => model.dispose();
    decoding = 'greedy Arabic transcription; max_new_tokens 128; no reference prompt';
    timer_scope = 'Transformers.js pipeline call; includes features, generation and text decoding';
  } else {
    throw new Error('Unknown adapter');
  }
  const load_seconds = (performance.now() - started) / 1000;
  const runs = [];
  try {
    for (let n = 0; n < config.warmups + config.repeats; n++) {
      const trial = await infer();
      if (n >= config.warmups) runs.push(trial);
    }
    const packageVersion = name => JSON.parse(readFileSync(new URL(
      `../../experiments/ikhlas-test/node_modules/${name}/package.json`, import.meta.url), 'utf8')).version;
    process.stdout.write(JSON.stringify({ load_seconds, runs, decoding, timer_scope,
      runtime: { node: process.version, onnxruntime_node: packageVersion('onnxruntime-node'),
        transformers_js: packageVersion('@huggingface/transformers') } }));
  } finally {
    audio.fill(0);
    pcm.fill(0);
    await release();
  }
}

main().catch(() => { process.stderr.write('Local inference failed.\n'); process.exitCode = 1; });
