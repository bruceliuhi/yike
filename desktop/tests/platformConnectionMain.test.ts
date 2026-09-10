import {beforeAll,expect,it,vi} from 'vitest';
import path from 'node:path';
const m=vi.hoisted(()=>{
 const frame={url:'yike://app/index.html'},contents={mainFrame:null as any,on:vi.fn(),setWindowOpenHandler:vi.fn()};contents.mainFrame=frame;
 const window={webContents:contents,once:vi.fn(),loadURL:vi.fn().mockResolvedValue(undefined),isDestroyed:()=>false};
 let stop!:()=>void;const stopped=new Promise<void>(resolve=>stop=resolve);
 return {frame,window,handlers:new Map<string,Function>(),events:new Map<string,Function>(),mkdir:vi.fn().mockResolvedValue(undefined),
  controller:vi.fn(),replyController:vi.fn(),replyExecute:vi.fn().mockResolvedValue({state:'SYNCED'}),replyStop:vi.fn(()=>stopped),driver:vi.fn().mockReturnValue({login:true}),store:vi.fn().mockReturnValue({store:true}),
  execute:vi.fn().mockResolvedValue({state:'OPENED',flowId:'flow'}),shutdown:vi.fn(()=>stopped),stop,
  quit:vi.fn(),error:vi.fn(),service:{request:vi.fn(),requestDevice:vi.fn(),requestConnection:vi.fn()}};
});
vi.mock('node:fs/promises',async original=>({...await original<typeof import('node:fs/promises')>(),mkdir:m.mkdir}));
vi.mock('electron-squirrel-startup',()=>({default:false}));
vi.mock('electron',()=>({
 app:{whenReady:()=>Promise.resolve(),on:(name:string,fn:Function)=>m.events.set(name,fn),quit:m.quit,isPackaged:false,
  getPath:()=>path.resolve('TEST-platform-main-user-data'),getVersion:()=> 'test',requestSingleInstanceLock:()=>true,setAppUserModelId:vi.fn()},
 BrowserWindow:class {constructor(){return m.window;}static getAllWindows(){return [m.window];}},
 safeStorage:{isEncryptionAvailable:()=>true,encryptString:vi.fn(),decryptString:vi.fn()},clipboard:{},dialog:{showErrorBox:m.error},shell:{},net:{},
 ipcMain:{handle:(name:string,fn:Function)=>m.handlers.set(name,fn)},
 Menu:{setApplicationMenu:vi.fn(),buildFromTemplate:()=>[]},screen:{getPrimaryDisplay:()=>({workAreaSize:{width:1440,height:900}})},
 protocol:{registerSchemesAsPrivileged:vi.fn(),handle:vi.fn().mockResolvedValue(undefined)},
 session:{defaultSession:{setPermissionCheckHandler:vi.fn(),setPermissionRequestHandler:vi.fn(),on:vi.fn()},fromPartition:()=>({setPermissionCheckHandler:vi.fn(),setPermissionRequestHandler:vi.fn(),fetch:vi.fn(),clearStorageData:vi.fn()})},
}));
vi.mock('../src/main/rendererAssets',()=>({CONTENT_SECURITY_POLICY:'test',loadRendererAssets:()=>new Set()}));
vi.mock('../src/main/serviceClient',async original=>({...await original<typeof import('../src/main/serviceClient')>(),createServiceClient:()=>m.service}));
vi.mock('../src/main/platformConnectionController',()=>({createPlatformConnectionController:(options:any)=>{m.controller(options);return {execute:m.execute,shutdown:m.shutdown};}}));
vi.mock('../src/main/platformLoginDriver',()=>({createPlatformLoginDriver:m.driver}));
// This is a main wiring fixture, not a claim that Windows profiles run on macOS.
vi.mock('../src/main/platformLoginConfiguration',()=>({platformLoginConfiguration:()=>({
 pythonExecutable:path.resolve('python.exe'),projectRoot:path.resolve('project'),runtimePath:path.resolve('runtime'),
 profileRoot:path.resolve('TEST-platform-main-user-data','platform-profiles'),outputRoot:path.resolve('TEST-platform-main-user-data','platform-login-output'),
})}));
vi.mock('../src/main/connectionProfileStore',()=>({createConnectionProfileStore:m.store}));
vi.mock('../src/main/nativeReplyController',()=>({createNativeReplyController:(options:any)=>{m.replyController(options);return {execute:m.replyExecute,stop:m.replyStop};}}));
beforeAll(async()=>{
 vi.stubEnv('YIKE_SERVICE_URL','http://127.0.0.1:9800');vi.stubEnv('YIKE_ALLOW_LOOPBACK_HTTP','1');
 vi.stubEnv('YIKE_SOURCE_HOST_PYTHON',path.resolve('python.exe'));vi.stubEnv('YIKE_SOURCE_PROJECT_ROOT',path.resolve('project'));vi.stubEnv('YIKE_SOURCE_RUNTIME_PATH',path.resolve('runtime'));
 await import('../src/main/main');await vi.waitFor(()=>expect(m.handlers.has('desktop:platform-connection-command')).toBe(true));vi.unstubAllEnvs();
});
it('assembles fixed trusted connection command with the same identity controller and OS protection',async()=>{
 const options=m.controller.mock.calls[0][0];expect(options).toMatchObject({serviceOrigin:'http://127.0.0.1:9800',store:{store:true},login:{login:true}});
 expect(options.identity.openWorkerScope).toBeTypeOf('function');
 expect(m.store.mock.calls[0][0]).toMatchObject({directory:path.resolve('TEST-platform-main-user-data','platform-connection-records'),protection:{encryptString:expect.any(Function)}});
 expect(m.driver.mock.calls[0][0]).toMatchObject({profileRoot:path.resolve('TEST-platform-main-user-data','platform-profiles'),outputRoot:path.resolve('TEST-platform-main-user-data','platform-login-output')});
 const command={action:'OPEN',platform:'XIAOHONGSHU'};await m.handlers.get('desktop:platform-connection-command')!({sender:m.window.webContents,senderFrame:m.frame},command);expect(m.execute).toHaveBeenCalledWith(command);
 expect(m.handlers.get('desktop:get-runtime-status')!({sender:m.window.webContents,senderFrame:m.frame})).toEqual({state:'FAILED',errorCode:'LOCAL_SERVICE_UNAVAILABLE'});
});
it('assembles reply sync with the same identity/profile store and trusted-only IPC',async()=>{
 const options=m.replyController.mock.calls[0][0],connection=m.controller.mock.calls[0][0];
 expect(options.identity).toBe(connection.identity);expect(options.store).toBe(connection.store);expect(options.driver).toBeTypeOf('function');
 const invoke=m.handlers.get('desktop:native-reply')!,command={action:'SYNC',opportunityId:'test-hint',requestId:'test-hint'};
 await invoke({sender:m.window.webContents,senderFrame:m.frame},command);expect(m.replyExecute).toHaveBeenCalledWith(command);
 expect(()=>invoke({sender:m.window.webContents,senderFrame:{url:'https://evil.example'}},command)).toThrow();
 expect(m.replyExecute).toHaveBeenCalledTimes(1);
});
it('quit waits once for the physical login and reply stop before completing application exit',async()=>{
 const preventDefault=vi.fn(),beforeQuit=m.events.get('before-quit')!;beforeQuit({preventDefault});beforeQuit({preventDefault});
 expect(preventDefault).toHaveBeenCalledTimes(2);expect(m.shutdown).toHaveBeenCalledTimes(1);expect(m.quit).not.toHaveBeenCalled();
 expect(m.replyStop).toHaveBeenCalledTimes(1);
 m.stop();await vi.waitFor(()=>expect(m.quit).toHaveBeenCalledTimes(1));beforeQuit({preventDefault});expect(preventDefault).toHaveBeenCalledTimes(2);expect(m.error).not.toHaveBeenCalled();
});
