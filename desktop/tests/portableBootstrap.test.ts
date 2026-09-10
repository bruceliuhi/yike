import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
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
  const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify,spawn:spawn as any,prepareParent:async()=>{}});
  const done=b.start();await vi.waitFor(()=>expect(spawn).toHaveBeenCalledOnce());
  expect(verify).toHaveBeenCalledOnce();expect(b.status()).toEqual({state:'PREPARING'});
  p.stdout.write(JSON.stringify({state:'READY',manifestSha256:'a'.repeat(64)})+'\n');
  expect(b.status()).toEqual({state:'PREPARING'});p.emit('close',0);
  await expect(done).resolves.toMatchObject({pythonExecutable:expect.stringContaining('host/python.exe')});
  expect(b.status()).toEqual({state:'READY'});
});
it('never executes a payload that failed integrity',async()=>{
  const spawn=vi.fn();const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify:async()=>{throw Error();},spawn:spawn as any,prepareParent:async()=>{}});
  await expect(b.start()).resolves.toBeNull();expect(spawn).not.toHaveBeenCalled();expect(b.status()).toEqual({state:'FAILED'});
});
it('cancels preparation and ignores late READY',async()=>{
  const p=child(),spawn=vi.fn(()=>p as any);const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify:async()=>{},spawn:spawn as any,prepareParent:async()=>{}});
  const start=b.start();await vi.waitFor(()=>expect(spawn).toHaveBeenCalledOnce());const stopping=b.stop();
  expect(p.kill).toHaveBeenCalled();p.stdout.write(JSON.stringify({state:'READY',manifestSha256:'a'.repeat(64)})+'\n');p.emit('close',0);
  await stopping;await expect(start).resolves.toBeNull();expect(b.status()).toEqual({state:'FAILED'});
});
it('does not confirm stop without a physical close',async()=>{
  const p=child(),spawn=vi.fn(()=>p as any);const b=createPortableBootstrap({resourcesPath:'/resources',userData:'/userdata',pin:{sha256:'a'.repeat(64),resourceName:'yike-portable'},verify:async()=>{},spawn:spawn as any,prepareParent:async()=>{}});
  const start=b.start();await vi.waitFor(()=>expect(spawn).toHaveBeenCalledOnce());vi.useFakeTimers();
  try {const failure=expect(b.stop()).rejects.toThrow('PORTABLE_STOP_UNCONFIRMED');await vi.advanceTimersByTimeAsync(5501);await failure;
    await expect(start).resolves.toBeNull();expect(b.status()).toEqual({state:'FAILED'});
  }finally{p.emit('close',1);vi.useRealTimers();}
});
