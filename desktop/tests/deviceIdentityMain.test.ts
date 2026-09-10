import {beforeAll, expect, it, vi} from 'vitest';
import path from 'node:path';
const mocks = vi.hoisted(()=>{
  const handlers = new Map<string, (...args:any[])=>any>();
  const frame = {url:'yike://app/index.html'};
  const contents = {mainFrame:frame,on:vi.fn(),setWindowOpenHandler:vi.fn()};
  const window = {webContents:contents,once:vi.fn(),loadURL:vi.fn().mockResolvedValue(undefined),isDestroyed:()=>false};
  return {handlers,frame,window,request:vi.fn().mockResolvedValue({ok:true,status:200,data:{authenticated:true,user_id:'verified-user'}}),
    requestDevice:vi.fn(),prepare:vi.fn().mockResolvedValue({state:'READY',deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1}),
    coordinator:vi.fn(),journal:vi.fn().mockReturnValue({journal:true}),vault:vi.fn().mockReturnValue({vault:true}),
    executionJournal:vi.fn().mockReturnValue({executionJournal:true}), executionSession:vi.fn(),
    executionList:vi.fn().mockResolvedValue({state:'LIST',requests:[]}),
    safeStorage:{isEncryptionAvailable:()=>true,encryptString:vi.fn(),decryptString:vi.fn()},quit:vi.fn()};
});
vi.mock('../src/main/executionJournal',()=>({createExecutionJournal:mocks.executionJournal}));
vi.mock('../src/main/executionSession',()=>({createExecutionSession:(options:any)=>{
  mocks.executionSession(options); return {list:mocks.executionList,submit:vi.fn(),recover:vi.fn()};
}}));
vi.mock('electron-squirrel-startup',()=>({default:false}));
vi.mock('electron',()=>({
  app:{whenReady:()=>Promise.resolve(),on:vi.fn(),quit:mocks.quit,isPackaged:false,getPath:()=>path.resolve('TEST-device-main-user-data'),getVersion:()=> 'test',requestSingleInstanceLock:()=>true,setAppUserModelId:vi.fn()},
  BrowserWindow:class {constructor(){return mocks.window;} static getAllWindows(){return [mocks.window];}},
  safeStorage:mocks.safeStorage, clipboard:{},dialog:{showErrorBox:vi.fn()},shell:{},net:{},
  ipcMain:{handle:(name:string,fn:(...args:any[])=>any)=>mocks.handlers.set(name,fn)},
  Menu:{setApplicationMenu:vi.fn(),buildFromTemplate:()=>[]},screen:{getPrimaryDisplay:()=>({workAreaSize:{width:1440,height:900}})},
  protocol:{registerSchemesAsPrivileged:vi.fn(),handle:vi.fn().mockResolvedValue(undefined)},
  session:{defaultSession:{setPermissionCheckHandler:vi.fn(),setPermissionRequestHandler:vi.fn(),on:vi.fn()},
    fromPartition:()=>({setPermissionCheckHandler:vi.fn(),setPermissionRequestHandler:vi.fn(),fetch:vi.fn(),clearStorageData:vi.fn()})},
}));
vi.mock('../src/main/rendererAssets',()=>({CONTENT_SECURITY_POLICY:'test',loadRendererAssets:()=>new Set()}));
vi.mock('../src/main/serviceClient',async importOriginal=>({...await importOriginal<typeof import('../src/main/serviceClient')>(),
  createServiceClient:()=>({request:mocks.request,requestDevice:mocks.requestDevice})}));
vi.mock('../src/main/deviceIdentityJournal',()=>({createDeviceIdentityJournal:mocks.journal}));
vi.mock('../src/main/deviceKeyVault',()=>({createDeviceKeyVault:mocks.vault}));
vi.mock('../src/main/deviceIdentitySession',()=>({createDeviceIdentitySession:(options:unknown)=>{mocks.coordinator(options);return {prepare:mocks.prepare};}}));
beforeAll(async()=>{
  vi.stubEnv('YIKE_SERVICE_URL','http://127.0.0.1:9800');vi.stubEnv('YIKE_ALLOW_LOOPBACK_HTTP','1');
  await import('../src/main/main');
  await vi.waitFor(()=>expect(mocks.handlers.has('desktop:request-api')).toBe(true));
  vi.unstubAllEnvs();
});
const trusted=()=>({sender:mocks.window.webContents,senderFrame:mocks.frame});
it('installs normal trusted identity handlers with fixed userData vault and journal',async()=>{
  expect(mocks.handlers.has('desktop:prepare-device-identity')).toBe(true);
  const result=await mocks.handlers.get('desktop:prepare-device-identity')!(trusted(),{});
  expect(result.state).toBe('READY');
  expect(mocks.request).toHaveBeenCalledWith({operation:'session.get'});
  expect(mocks.prepare.mock.calls[0][0]).toMatchObject({userId:'verified-user'});
  expect(mocks.journal.mock.calls[0][0].directory).toBe(path.resolve('TEST-device-main-user-data','device-identity'));
  expect(mocks.vault.mock.calls[0][0].directory).toBe(path.resolve('TEST-device-main-user-data','device-keys'));
  expect(mocks.coordinator.mock.calls[0][0]).toMatchObject({deviceLabel:'意客AI Windows客户端',serviceOrigin:'http://127.0.0.1:9800'});
  expect(await mocks.handlers.get('desktop:get-runtime-status')!(trusted())).toEqual({state:'FAILED',errorCode:'LOCAL_SERVICE_UNAVAILABLE'});
  expect(mocks.quit).not.toHaveBeenCalled();
});
it('rejects subframes, foreign windows and URLs on identity and execution channels',()=>{
  for(const channel of ['desktop:get-device-identity-status','desktop:prepare-device-identity','desktop:execution-command','desktop:platform-connection-command']){
    expect(mocks.handlers.has(channel)).toBe(true);
    const handler=mocks.handlers.get(channel)!;
    expect(()=>handler({...trusted(),senderFrame:{url:'https://evil.invalid'}},{})).toThrow('UNTRUSTED_DESKTOP_SENDER');
    expect(()=>handler({...trusted(),senderFrame:{url:mocks.frame.url}},{})).toThrow('UNTRUSTED_DESKTOP_SENDER');
    expect(()=>handler({sender:{mainFrame:mocks.frame},senderFrame:mocks.frame},{})).toThrow('UNTRUSTED_DESKTOP_SENDER');
  }
});
it('leaves login unavailable without main-owned developer runtime configuration',async()=>{
  const handler=mocks.handlers.get('desktop:platform-connection-command');expect(handler).toBeTypeOf('function');
  expect(await handler!(trusted(),{action:'OPEN',platform:'XIAOHONGSHU'})).toEqual({state:'SERVICE_UNAVAILABLE'});
});
it('assembles execution on the normal identity epoch and fixed protected userData journal', async()=>{
  const handler=mocks.handlers.get('desktop:execution-command');
  expect(handler).toBeTypeOf('function');
  expect(await handler!(trusted(),{action:'LIST'})).toEqual({state:'LIST',requests:[]});
  expect(mocks.executionJournal.mock.calls[0][0].directory).toBe(path.resolve('TEST-device-main-user-data','execution-operations'));
  expect(mocks.executionSession.mock.calls[0][0]).toMatchObject({serviceOrigin:'http://127.0.0.1:9800',journal:{executionJournal:true}});
  expect(mocks.executionList.mock.calls.at(-1)![0]).toMatchObject({userId:'verified-user',isCurrent:expect.any(Function)});
});
it('routes ordinary logout through controller to clear last identity observation immediately',async()=>{
  expect(mocks.handlers.has('desktop:prepare-device-identity')).toBe(true);
  await mocks.handlers.get('desktop:prepare-device-identity')!(trusted(),{});
  const pending=mocks.handlers.get('desktop:request-api')!(trusted(),{operation:'session.logout'});
  expect(mocks.handlers.get('desktop:get-device-identity-status')!(trusted()).state).not.toBe('READY');
  await pending;
});
