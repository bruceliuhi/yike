import {defineConfig} from 'vite';

export default defineConfig({
  root: 'src/renderer',
  base: './',
  build: {
    outDir: '../../.vite/renderer/main_window',
    emptyOutDir: true,
    manifest: true
  }
});
