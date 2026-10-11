import { execFileSync } from 'node:child_process';
const root = new URL('../../../', import.meta.url);
execFileSync('cargo', ['build', '--locked', '--release', '--target', 'wasm32-unknown-unknown', '-p', 'hifz-core'], { cwd: root, stdio: 'inherit' });
execFileSync('wasm-bindgen', ['--target', 'web', '--out-dir', 'experiments/ikhlas-test/rust-pkg', 'target/wasm32-unknown-unknown/release/hifz_core.wasm'], { cwd: root, stdio: 'inherit' });
