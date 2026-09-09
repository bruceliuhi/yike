import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';

const desktop = fileURLToPath(new URL('.', import.meta.url));
export default defineConfig({
  root: fileURLToPath(new URL('./tests/visual', import.meta.url)),
  server: {host: '127.0.0.1', port: 18794, strictPort: true, fs: {allow: [desktop]},
    headers: {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:18794; object-src 'none'; frame-src 'none'; worker-src 'none'; form-action 'none'; base-uri 'none'"}},
  // Deliberately separate from .vite/renderer and the Forge renderer entry.
  build: {outDir: '../../out/visual-harness', emptyOutDir: true, manifest: true},
});
