import type {ForgeConfig} from '@electron-forge/shared-types';
import {VitePlugin} from '@electron-forge/plugin-vite';

const config: ForgeConfig = {
  packagerConfig: {
    appBundleId: 'net.xingheai.yike.desktop',
    name: '意客 AI',
    asar: true
  },
  makers: [],
  plugins: [new VitePlugin({
    build: [
      {entry: 'src/main/main.ts', config: 'vite.main.config.ts'},
      {entry: 'src/preload/index.ts', config: 'vite.preload.config.ts'}
    ],
    renderer: [{name: 'main_window', config: 'vite.renderer.config.ts'}]
  })]
};

export default config;
