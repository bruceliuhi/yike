import {defineConfig} from 'vite';

export default defineConfig({
  plugins:[{name:'dev-csp',apply:'serve',transformIndexHtml(html){return html.replace(/<meta\s+http-equiv="Content-Security-Policy"[^>]*>/i,'');}}],
  root: 'src/renderer',
  base: './',
  server: {
    host: '127.0.0.1',
    port: 18791,
    strictPort: true,
    proxy: process.env.YIKE_DEV_API_TARGET ? {'/api/ui': {target:process.env.YIKE_DEV_API_TARGET,changeOrigin:true}} : undefined
  },
  build: {
    outDir: '../../.vite/renderer/main_window',
    emptyOutDir: true,
    manifest: true,
    assetsInlineLimit: 0
  }
});
