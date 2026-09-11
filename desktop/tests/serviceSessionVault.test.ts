import {afterEach,expect,it,vi} from 'vitest';
import {mkdtemp,readFile,readdir,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createCipheriv,createDecipheriv,randomBytes} from 'node:crypto';
import {createServiceSessionVault} from '../src/main/serviceSessionVault';

const directories:string[]=[];
afterEach(async()=>{await Promise.all(directories.splice(0).map(directory=>rm(directory,{recursive:true,force:true})));});
async function fixture(){
  const directory=await mkdtemp(path.join(os.tmpdir(),'yike-session-vault-'));directories.push(directory);
  const key=randomBytes(32);
  const protection={isEncryptionAvailable:()=>true,
    encryptString(value:string){const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv);
      return Buffer.concat([iv,cipher.update(value),cipher.final(),cipher.getAuthTag()]);},
    decryptString(value:Buffer){const decipher=createDecipheriv('aes-256-gcm',key,value.subarray(0,12));decipher.setAuthTag(value.subarray(-16));
      return Buffer.concat([decipher.update(value.subarray(12,-16)),decipher.final()]).toString();}};
  const origin='https://pilot.example';
  return {directory,protection,origin,vault:createServiceSessionVault({directory,protection,origin})};
}
const cookie=()=>({name:'pilot_session',value:'synthetic-signed-session-only',domain:'pilot.example',path:'/',
  secure:true,httpOnly:true,hostOnly:true,sameSite:'strict',expirationDate:Date.now()/1000+3600});
it('persists only encrypted origin-bound session and restores after factory restart',async()=>{
  const f=await fixture(),value=cookie();await f.vault.save(value);
  const files=await readdir(f.directory);expect(files).toHaveLength(1);
  expect((await readFile(path.join(f.directory,files[0]))).includes(Buffer.from(value.value))).toBe(false);
  expect(await createServiceSessionVault(f).read()).toEqual({value:value.value,expiresAt:value.expirationDate});
  expect(await createServiceSessionVault({...f,origin:'https://other.example'}).read()).toBeNull();
  await f.vault.clear();expect(await f.vault.read()).toBeNull();
});
it('rejects wrong cookie scope and unavailable OS encryption without writing plaintext',async()=>{
  const f=await fixture();
  for(const bad of [{...cookie(),httpOnly:false},{...cookie(),secure:false},{...cookie(),domain:'other.example'},
    {...cookie(),path:'/ops'},{...cookie(),name:'yike_ops_session'},{...cookie(),expirationDate:0}])
    await expect(f.vault.save(bad)).rejects.toThrow('SESSION_PERSIST_FAILED');
  const unsafe=createServiceSessionVault({...f,protection:{...f.protection,isEncryptionAvailable:()=>false}});
  await expect(unsafe.save(cookie())).rejects.toThrow('SESSION_PERSIST_FAILED');
  expect(await readdir(f.directory)).toEqual([]);
});
it('does not restore expired ciphertext and never returns corrupted plaintext',async()=>{
  const f=await fixture(),value=cookie();await f.vault.save(value);
  vi.spyOn(Date,'now').mockReturnValue((value.expirationDate+1)*1000);
  try{expect(await f.vault.read()).toBeNull();}finally{vi.restoreAllMocks();}
  const broken=createServiceSessionVault({...f,protection:{...f.protection,decryptString:()=>'{bad'}});
  await expect(broken.read()).rejects.toThrow('SESSION_RESTORE_FAILED');
});
