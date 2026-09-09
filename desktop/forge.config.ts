import type {ForgeConfig} from '@electron-forge/shared-types';
import {VitePlugin} from '@electron-forge/plugin-vite';
import {MakerZIP} from '@electron-forge/maker-zip';
import {AsciiStagingSquirrelMaker} from './build/asciiStagingSquirrel';
import {resolve} from 'node:path';

const config: ForgeConfig = {
  packagerConfig: {
    appBundleId: 'net.xingheai.yike.desktop',
    name: '意客AI',
    executableName: 'YikeAI',
    icon: resolve('assets/yike'),
    appCategoryType: 'public.app-category.business',
    asar: true
  },
  makers: [
    new MakerZIP({}, ['darwin']),
    new AsciiStagingSquirrelMaker({
      name: 'YikeAI', authors: '星河科技', description: '意客AI商机工作台',
      exe: 'YikeAI.exe', setupExe: 'YikeAI-Setup.exe', setupIcon: resolve('assets/yike.ico'), noMsi: true
    })
  ],
  plugins: [new VitePlugin({
    build: [
      {entry: 'src/main/main.ts', config: 'vite.main.config.ts', target: 'main'},
      {entry: 'src/preload/index.ts', config: 'vite.preload.config.ts', target: 'preload'}
    ],
    renderer: [{name: 'main_window', config: 'vite.renderer.config.ts'}]
  })]
};

export default config;
