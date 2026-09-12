import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import path from 'node:path';
import {expect,it,vi} from 'vitest';
import {createPortableBootstrap,publishedPortableStatus} from '../src/main/portableBootstrap';
function child(){const p=Object.assign(new EventEmitter(),{stdout:new PassThrough(),stderr:new PassThrough(),kill:vi.fn(()=>true)});return p;}
it('does not publish ready before controller attachment, including delayed attachment failure',()=>{
  expect(publishedPortableStatus({state:'READY'},false,false)).toEqual({state:'PREPARING'});
  expect(publishedPortableStatus({state:'READY'},false,true)).toEqual({state:'FAILED'});
  expect(publishedPortableStatus({state:'READY'},true,false)).toEqual({state:'READY'});
});
it('verifies before spawning and waits for physical close after exact READY',async()=>{
  const p=child(),verify=vi.fn(async()=>{}),spawn=vi.fn(()=>p as any);
  const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify,spawn:spawn as any,prepareParent:async()=>{},resolveParent:p=>p});
  const done=b.start();await vi.waitFor(()=>expect(spawn).toHaveBeenCalledOnce());
  expect(verify).toHaveBeenCalledOnce();expect(b.status()).toEqual({state:'PREPARING'});
  p.stdout.write(JSON.stringify({state:'READY',manifestSha256:'a'.repeat(64)})+'\n');
  expect(b.status()).toEqual({state:'PREPARING'});p.emit('close',0);
  await expect(done).resolves.toMatchObject({pythonExecutable:path.join('/userdata','r','a'.repeat(64),'host','python.exe')});
  expect(b.status()).toEqual({state:'READY'});
});
it('installs into a short native path while preserving account and profile storage',async()=>{
  const p=child(),verify=vi.fn(async()=>{}),spawn=vi.fn(()=>p as any);
  const physicalParent=path.join('/physical-package-cache','userdata','r');
  const resolveParent=vi.fn(()=>physicalParent),prepareParent=vi.fn(async()=>{});
  const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',
    pin:{sha256:'b'.repeat(64),resourceName:'yike-portable'},verify,spawn:spawn as any,
    prepareParent,resolveParent});
  const done=b.start();await vi.waitFor(()=>expect(spawn).toHaveBeenCalledOnce());
  p.stdout.write(JSON.stringify({state:'READY',manifestSha256:'b'.repeat(64)}));p.emit('close',0);
  const destination=path.join(physicalParent,'b'.repeat(64));
  await expect(done).resolves.toMatchObject({
    pythonExecutable:path.join(destination,'host','python.exe'),
    projectRoot:path.join(destination,'project'),runtimePath:path.join(destination,'runtime'),
    profileRoot:path.join('/userdata','platform-profiles'),outputRoot:path.join('/userdata','platform-login-output'),
  });
  expect(prepareParent).toHaveBeenCalledWith(path.join('/userdata','r'));
  expect(resolveParent).toHaveBeenCalledWith(path.join('/userdata','r'));
  expect(spawn).toHaveBeenCalledWith(expect.any(String),expect.arrayContaining([destination]),expect.any(Object));
  expect(verify).toHaveBeenLastCalledWith(destination,'b'.repeat(64),expect.any(AbortSignal));
});
it('fails closed when the physical install parent cannot be resolved',async()=>{
  const spawn=vi.fn();
  const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',
    pin:{sha256:'c'.repeat(64),resourceName:'yike-portable'},verify:async()=>{},spawn:spawn as any,
    prepareParent:async()=>{},resolveParent:()=>{throw Error('unavailable');}});
  await expect(b.start()).resolves.toBeNull();
  expect(spawn).not.toHaveBeenCalled();expect(b.status()).toEqual({state:'FAILED'});
});
it('never executes a payload that failed integrity',async()=>{
  const spawn=vi.fn();const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify:async()=>{throw Error();},spawn:spawn as any,prepareParent:async()=>{}});
  await expect(b.start()).resolves.toBeNull();expect(spawn).not.toHaveBeenCalled();expect(b.status()).toEqual({state:'FAILED'});
});
it('cancels preparation and ignores late READY',async()=>{
  const p=child(),spawn=vi.fn(()=>p as any);const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify:async()=>{},spawn:spawn as any,prepareParent:async()=>{},resolveParent:p=>p});
  const start=b.start();await vi.waitFor(()=>expect(spawn).toHaveBeenCalledOnce());const stopping=b.stop();
  expect(p.kill).toHaveBeenCalled();p.stdout.write(JSON.stringify({state:'READY',manifestSha256:'a'.repeat(64)})+'\n');p.emit('close',0);
  await stopping;await expect(start).resolves.toBeNull();expect(b.status()).toEqual({state:'FAILED'});
});
it('does not confirm stop without a physical close',async()=>{
  const p=child(),spawn=vi.fn(()=>p as any);const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify:async()=>{},spawn:spawn as any,prepareParent:async()=>{},resolveParent:p=>p});
  const start=b.start();await vi.waitFor(()=>expect(spawn).toHaveBeenCalledOnce());vi.useFakeTimers();
  try {const failure=expect(b.stop()).rejects.toThrow('PORTABLE_STOP_UNCONFIRMED');await vi.advanceTimersByTimeAsync(5501);await failure;
    await expect(start).resolves.toBeNull();expect(b.status()).toEqual({state:'FAILED'});
  }finally{p.emit('close',1);vi.useRealTimers();}
});
