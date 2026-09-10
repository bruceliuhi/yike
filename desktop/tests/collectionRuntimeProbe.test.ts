import {afterEach,expect,it,vi} from 'vitest';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {probeCollectionRuntime} from '../src/main/collectionRuntimeProbe';
afterEach(()=>vi.useRealTimers());
function fixture(){const child=Object.assign(new EventEmitter(),{stdin:new PassThrough(),stdout:new PassThrough(),stderr:new PassThrough(),kill:vi.fn()});const spawn=vi.fn(()=>child);const result=probeCollectionRuntime({pythonExecutable:'C:/private/python.exe',projectRoot:'C:/product',runtimePath:'C:/runtime',spawn:spawn as unknown as typeof import('node:child_process').spawn});return {child,spawn,result};}
it('probes only the fixed private runtime host and waits actual close before READY',async()=>{
 const f=fixture();await Promise.resolve();let done=false;void f.result.then(()=>done=true);
 expect(f.spawn).toHaveBeenCalledWith('C:/private/python.exe',['-X','utf8','-m','app.windows_source_probe'],expect.objectContaining({cwd:'C:/product',shell:false,windowsHide:true}));
 expect(f.child.stdin.read().toString()).toBe(JSON.stringify({schema_version:'windows-source-probe-v1',runtime_path:'C:/runtime'})+'\n');
 f.child.stdout.write('{"schema_version":"windows-source-probe-v1","state":"READY"}\n');await Promise.resolve();expect(done).toBe(false);f.child.emit('close',0,null);expect(await f.result).toBe(true);
});
it.each(['extra','badexit','missing','oversize'])('does not grant availability on %s',async scenario=>{
 const f=fixture();await Promise.resolve();if(scenario!=='missing')f.child.stdout.write(scenario==='oversize'?'x'.repeat(17000):JSON.stringify({schema_version:'windows-source-probe-v1',state:'READY',...(scenario==='extra'?{path:'secret'}:{})})+'\n');
 f.child.emit('close',scenario==='badexit'?1:0,null);expect(await f.result).toBe(false);
});
it('times out a read-only probe without granting availability',async()=>{
 vi.useFakeTimers();const f=fixture();await Promise.resolve();await vi.advanceTimersByTimeAsync(30000);expect(await f.result).toBe(false);expect(f.child.kill).toHaveBeenCalledTimes(1);
});
