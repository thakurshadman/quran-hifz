import { defineConfig } from 'vite';

// The worker explicitly uses the locally copied, non-asyncify WASM runtime.
// Transformers' bundled fallback also emits a 27 MB asyncify binary which this
// experiment never loads. Exclude that unused fallback from the static package.
const omitUnusedRuntime = () => ({
  name: 'omit-unused-asyncify-runtime',
  generateBundle(_options, bundle) {
    for (const [name, entry] of Object.entries(bundle)) {
      if (entry.type === 'asset' && /^.*ort-wasm-simd-threaded\.asyncify.*\.wasm$/.test(name)) delete bundle[name];
    }
  },
});

export default defineConfig({
  plugins: [omitUnusedRuntime()],
  worker: { plugins: () => [omitUnusedRuntime()] },
});
