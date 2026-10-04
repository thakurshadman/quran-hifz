import { mkdir, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('../', import.meta.url);
const target = new URL('public/runtime/', root);
await mkdir(target, { recursive: true });
for (const name of ['ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.wasm']) {
  await copyFile(new URL(`node_modules/onnxruntime-web/dist/${name}`, root), new URL(name, target));
}
await copyFile(new URL('node_modules/@huggingface/transformers/LICENSE', root), new URL('public/TRANSFORMERS-LICENSE.txt', root));
console.log(`Prepared local speech runtime in ${fileURLToPath(target)}`);
