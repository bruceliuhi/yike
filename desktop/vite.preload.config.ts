import {defineConfig} from 'vite';

export default defineConfig({
  build: {
    rollupOptions: {
      output: {format: 'cjs', entryFileNames: 'preload.cjs', inlineDynamicImports: true}
    }
  }
});
