import {defineConfig} from 'vite';
import {portableBuildInput} from './build/portableBuild';
import {releaseServiceBuildInput} from './build/releaseService';

export default defineConfig(({command})=>({
  define:{
    __YIKE_RELEASE_SERVICE_URL__:JSON.stringify(command==='build'?releaseServiceBuildInput(process.env,false):null),
    __YIKE_PORTABLE_PIN__:JSON.stringify(command==='build'&&!process.argv.includes('start')?portableBuildInput(process.env,process.platform)?.pin??null:null)
  },
  build: {
    lib: {entry: 'src/main/main.ts', formats: ['cjs'], fileName: () => 'main.cjs'}
  }
}));
