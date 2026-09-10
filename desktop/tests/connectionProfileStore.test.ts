import {afterEach, expect, it} from 'vitest';
import {mkdtemp, readFile, readdir, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createConnectionProfileStore} from '../src/main/connectionProfileStore';
const roots: string[] = [];
afterEach(async () => {for (const root of roots.splice(0)) {if (path.dirname(root) !== tmpdir() || !path.basename(root).startsWith('yike-profile-')) throw Error(); await rm(root, {recursive:true, force:true});}});
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const scope = {serviceOrigin:'https://pilot.example', userId:'owner', deviceId:id(1), platform:'XIAOHONGSHU' as const};
const protection = {isEncryptionAvailable:() => true, encryptString:(s:string) => Buffer.from(Buffer.from(s).map(b => b ^ 37)), decryptString:(b:Buffer) => Buffer.from(Buffer.from(b).map(n => n ^ 37)).toString()};
async function fixture() {const directory = await mkdtemp(path.join(tmpdir(), 'yike-profile-')); roots.push(directory); const options={directory,protection}; return {directory,options,store:createConnectionProfileStore(options)};}
const operation = (record:any) => ({request_id:id(2), action:'REGISTER' as const, device_id:scope.deviceId, connection_id:null, expected_connection_version:0,
  platform:scope.platform, account_public_id:'66c01234abcdef0123456789', session_ref:`vault://platform/${record.profileId}`});
it('persists protected pending identity and resumes original requests across factory restart', async () => {
  const f=await fixture(); const record=await f.store.open(scope); expect(record.state).toBe('PENDING');
  await f.store.setOperation(scope,record.flowId,operation(record));
  const restored=await createConnectionProfileStore(f.options).open(scope);
  expect(restored.flowId).toBe(record.flowId); expect(restored.registration).toEqual(operation(record));
  const wire=await readFile(path.join(f.directory,(await readdir(f.directory))[0])); expect(wire.toString()).not.toContain('vault://'); expect(wire.toString()).not.toContain('owner');
});
it('scopes profile references by server, user and device and serializes opens',async () => {
  const f=await fixture(); const [a,b]=await Promise.all([f.store.open(scope),f.store.open(scope)]); expect(a.flowId).toBe(b.flowId);
  for (const change of [{userId:'other'},{deviceId:id(9)},{serviceOrigin:'https://other.example'}]) expect((await f.store.open({...scope,...change})).profileId).not.toBe(a.profileId);
});
it('rejects rewriting an original operation or binding another profile',async () => {
  const f=await fixture(); const r=await f.store.open(scope); const op=operation(r); await f.store.setOperation(scope,r.flowId,op);
  await expect(f.store.setOperation(scope,r.flowId,{...op,request_id:id(8)})).rejects.toThrow();
  await expect(f.store.setOperation(scope,r.flowId,{...op,session_ref:'vault://platform/other'})).rejects.toThrow();
  expect((await f.store.read(scope))!.registration).toEqual(op);
});
it('only resolved flows may be replaced and old snapshots remain intact',async () => {
  const f=await fixture(); const r=await f.store.open(scope); await f.store.resolve(scope,r.flowId);
  const next=await f.store.open(scope); expect(next.profileId).not.toBe(r.profileId); expect(r.state).toBe('PENDING');
  await expect(f.store.resolve(scope,r.flowId)).rejects.toThrow();
});
it('corrupt records or unavailable protection fail closed without overwriting',async () => {
  const f=await fixture(); await f.store.open(scope); const file=path.join(f.directory,(await readdir(f.directory))[0]); await writeFile(file,'corrupt');
  await expect(f.store.open(scope)).rejects.toThrow(); expect(await readFile(file,'utf8')).toBe('corrupt');
  const unavailable=createConnectionProfileStore({...f.options,protection:{...protection,isEncryptionAvailable:() => false}});
  await expect(unavailable.open(scope)).rejects.toThrow();
});
