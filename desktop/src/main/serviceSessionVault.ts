/** Main-only OS-encrypted session cache. Never stores the invitation/access code. */
import {createHash,randomUUID} from 'node:crypto';
import {constants} from 'node:fs';
import {lstat,mkdir,open,rename,unlink} from 'node:fs/promises';
import path from 'node:path';
import type {DeviceKeyProtection} from './deviceKeyVault';

type SavedSession={value:string;expiresAt:number};
type SessionCookie={name:string;value:string;domain?:string;path?:string;secure?:boolean;httpOnly?:boolean;
  hostOnly?:boolean;sameSite?:string;expirationDate?:number};
const LIMIT=65_536;
const absent=(error:unknown)=>!!error&&typeof error==='object'&&'code' in error&&error.code==='ENOENT';

export function createServiceSessionVault({directory,origin,protection}:{directory:string;origin:string;protection:DeviceKeyProtection}){
  const url=new URL(origin);
  if(url.origin!==origin||url.protocol!=='https:'||url.username||url.password||!path.isAbsolute(directory)||path.resolve(directory)===path.parse(directory).root)
    throw new Error('SESSION_PERSIST_FAILED');
  const filename=path.join(directory,createHash('sha256').update(origin).digest('hex')+'.session');
  function protectedStorage(){if(!protection.isEncryptionAvailable())throw new Error();}
  async function privateDirectory(create=false){
    if(create)await mkdir(directory,{recursive:true,mode:0o700});
    const stat=await lstat(directory);if(!stat.isDirectory()||stat.isSymbolicLink())throw new Error();
  }
  function validSession(value:unknown):value is SavedSession{
    if(!value||typeof value!=='object')return false;
    const row=value as SavedSession;
    return Object.keys(value).sort().join(',')==='expiresAt,value'&&typeof row.value==='string'&&
      row.value.length>0&&row.value.length<=16_384&&!/[\x00-\x20\x7f;]/.test(row.value)&&
      typeof row.expiresAt==='number'&&Number.isFinite(row.expiresAt)&&row.expiresAt>0;
  }
  return {
    async read():Promise<SavedSession|null>{
      try{
        await privateDirectory();protectedStorage();
        const stat=await lstat(filename);if(!stat.isFile()||stat.isSymbolicLink()||stat.size<1||stat.size>LIMIT)throw new Error();
        const handle=await open(filename,constants.O_RDONLY|(constants.O_NOFOLLOW??0));
        let bytes:Buffer;
        try{const stat=await handle.stat();if(!stat.isFile()||stat.size<1||stat.size>LIMIT)throw new Error();
          bytes=Buffer.alloc(LIMIT+1);const {bytesRead}=await handle.read(bytes,0,bytes.length,0);bytes=bytes.subarray(0,bytesRead);
          if(bytes.length<1||bytes.length>LIMIT)throw new Error();
        }finally{await handle.close();}
        const record=JSON.parse(protection.decryptString(bytes));
        if(!record||record.version!==1||record.origin!==origin||Object.keys(record).sort().join(',')!=='origin,session,version'||!validSession(record.session))throw new Error();
        return record.session.expiresAt>Date.now()/1000?record.session:null;
      }catch(error){if(absent(error))return null;throw new Error('SESSION_RESTORE_FAILED');}
    },
    async save(cookie:SessionCookie):Promise<void>{
      let temporary:string|undefined;
      try{
        protectedStorage();
        const session={value:cookie.value,expiresAt:cookie.expirationDate};
        if(cookie.name!=='pilot_session'||cookie.domain!==url.hostname||cookie.path!=='/'||
          !cookie.secure||!cookie.httpOnly||cookie.hostOnly===false||cookie.sameSite!=='strict'||
          !validSession(session)||session.expiresAt<=Date.now()/1000)throw new Error();
        const bytes=protection.encryptString(JSON.stringify({version:1,origin,session}));
        if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>LIMIT)throw new Error();
        await privateDirectory(true);
        try{const current=await lstat(filename);if(!current.isFile()||current.isSymbolicLink())throw new Error();}
        catch(error){if(!absent(error))throw error;}
        temporary=path.join(directory,randomUUID()+'.tmp');
        const handle=await open(temporary,'wx',0o600);
        try{await handle.writeFile(bytes);await handle.sync();}finally{await handle.close();}
        await rename(temporary,filename);temporary=undefined;
      }catch{throw new Error('SESSION_PERSIST_FAILED');}
      finally{if(temporary)await unlink(temporary).catch(()=>undefined);}
    },
    async clear():Promise<void>{
      try{await privateDirectory();await unlink(filename);}
      catch(error){if(!absent(error))throw new Error('SESSION_CLEAR_FAILED');}
    },
  };
}
