import {z} from 'zod';
import {createHash, randomUUID} from 'node:crypto';
import {constants} from 'node:fs';
import {lstat, mkdir, open, rename} from 'node:fs/promises';
import path from 'node:path';
import type {DeviceKeyProtection} from './deviceKeyVault';
import {deviceUuidSchema as uuid} from '../shared/deviceRegistration';
import {connectionOperationSchema, type ConnectionOperation} from '../shared/connectionOperation';
const scopeSchema = z.object({serviceOrigin: z.string().max(2048).refine(s => {
  try {const u=new URL(s); return u.origin===s && !u.username && !u.password && (u.protocol==='https:' || u.protocol==='http:' && ['localhost','127.0.0.1','[::1]'].includes(u.hostname));} catch {return false;}
}), userId:z.string().min(1).refine(s => s.trim()===s && Array.from(s).length<=256 && !/[\p{Cc}\p{Cs}]/u.test(s)), deviceId:uuid, platform:z.literal('XIAOHONGSHU')}).strict();
export type ConnectionProfileScope = z.infer<typeof scopeSchema>;
const recordSchema=z.object({version:z.literal(1),scope:scopeSchema,flowId:uuid,profileId:uuid,state:z.enum(['PENDING','RESOLVED']),
  registration:connectionOperationSchema.nullable(),verification:connectionOperationSchema.nullable()}).strict();
export type ConnectionProfileRecord = z.infer<typeof recordSchema>;
const pending=new Map<string,Promise<unknown>>();
const MAX=65536;
const failure=() => new Error('CONNECTION_PROFILE_STORAGE_FAILED');
const same=(a:unknown,b:unknown) => JSON.stringify(a)===JSON.stringify(b);
function parse(value:unknown,scope:ConnectionProfileScope):ConnectionProfileRecord {
  const r=recordSchema.parse(value);
  if (!same(r.scope,scope)) throw failure();
  for (const [kind,op] of [['REGISTER',r.registration],['VERIFY',r.verification]] as const) if (op) {
    if (op.action!==kind || op.device_id!==scope.deviceId || op.platform!==scope.platform || op.session_ref!==`vault://platform/${r.profileId}`) throw failure();
  }
  if (r.verification && (!r.registration || r.registration.account_public_id!==r.verification.account_public_id)) throw failure();
  return r;
}
export function createConnectionProfileStore({directory,protection}:{directory:string;protection:DeviceKeyProtection}) {
  const root=path.resolve(directory);
  async function readFile(file:string,scope:ConnectionProfileScope) {
    let info;
    try {info=await lstat(file);} catch(e) {if ((e as NodeJS.ErrnoException).code==='ENOENT') return null; throw e;}
    if (!info.isFile() || info.isSymbolicLink() || info.nlink!==1 || info.size<1 || info.size>MAX) throw failure();
    const handle=await open(file,constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
    try {const actual=await handle.stat(); if(actual.dev!==info.dev || actual.ino!==info.ino || actual.nlink!==1 || actual.size>MAX) throw failure();
      return parse(JSON.parse(protection.decryptString(await handle.readFile())),scope);
    } finally {await handle.close();}
  }
  async function write(file:string,record:ConnectionProfileRecord) {
    const cipher=protection.encryptString(JSON.stringify(record));
    if (!Buffer.isBuffer(cipher) || !cipher.length || cipher.length>MAX) throw failure();
    const temporary=file+'.'+randomUUID()+'.tmp';
    const h=await open(temporary,'wx',0o600);
    try {await h.writeFile(cipher); await h.sync();} finally {await h.close();}
    await rename(temporary,file);
  }
  function transaction<T>(raw:ConnectionProfileScope,fn:(scope:ConnectionProfileScope,file:string,record:ConnectionProfileRecord|null)=>Promise<T>):Promise<T> {
    let scope:ConnectionProfileScope;
    try {scope=scopeSchema.parse(raw);} catch {return Promise.reject(failure());}
    const file=path.join(root,createHash('sha256').update(JSON.stringify(scope)).digest('hex')+'.profile');
    const task=(pending.get(file)??Promise.resolve()).catch(()=>{}).then(async()=>{
      if (!protection.isEncryptionAvailable()) throw failure();
      await mkdir(root,{recursive:true,mode:0o700}); const info=await lstat(root);
      if (!info.isDirectory() || info.isSymbolicLink()) throw failure();
      return fn(scope,file,await readFile(file,scope));
    }).catch(()=>{throw failure();});
    pending.set(file,task); void task.finally(()=>{if(pending.get(file)===task)pending.delete(file);}).catch(()=>{});
    return task;
  }
  return {
    read(scope:ConnectionProfileScope) {return transaction(scope,async(_s,_f,r)=>r);},
    open(scope:ConnectionProfileScope) {return transaction(scope,async(s,f,r)=>{
      if(r?.state==='PENDING') return r;
      if(r) {const archive=f+'.'+r.flowId+'.resolved'; const old=await readFile(archive,s); if(old && !same(old,r))throw failure(); if(!old)await write(archive,r);}
      const created:ConnectionProfileRecord={version:1,scope:s,flowId:randomUUID(),profileId:randomUUID(),state:'PENDING',registration:null,verification:null};
      await write(f,created); return created;
    });},
    setOperation(scope:ConnectionProfileScope,flowId:string,raw:ConnectionOperation) {return transaction(scope,async(s,f,r)=>{
      if(!r || r.flowId!==flowId || r.state!=='PENDING')throw failure();
      const op=connectionOperationSchema.parse(raw); if(op.action==='DISCONNECT')throw failure();
      const field=op.action==='REGISTER'?'registration':'verification';
      if(r[field] && !same(r[field],op))throw failure();
      const changed=parse({...r,[field]:op},s); await write(f,changed); return changed;
    });},
    resolve(scope:ConnectionProfileScope,flowId:string) {return transaction(scope,async(s,f,r)=>{
      if(!r || r.flowId!==flowId)throw failure();
      const changed=parse({...r,state:'RESOLVED'},s); await write(f,changed); return changed;
    });},
  };
}
