import {useEffect,useReducer} from 'react';
import {z} from 'zod';
import {nativeOutreachBindingSchema,type NativeOutreachBinding} from '../../../shared/nativeOutreach';
import type {Session} from '../../domain/models';

const recordSchema=z.object({binding:nativeOutreachBindingSchema,state:z.enum(['PENDING','SENT'])}).strict();
export type NativeOutreachRecord=z.infer<typeof recordSchema>;
const event='yike-native-outreach-ledger';
export const storageMessage='恢复记录无法可靠保存或读取，当前不会发送；请检查本机存储并核对原请求。';
export function nativeOutreachLedgerKey(session:Session,opportunityId:string,channel:string):string|null {
  if(!session.authenticated || !session.userId || !session.accountScope)return null;
  return 'yike.ui.native-outreach.v1.'+encodeURIComponent(JSON.stringify([session.userId,session.accountScope.id,session.accountScope.version,opportunityId,channel]));
}
export function readNativeOutreachRecord(key:string|null):NativeOutreachRecord|null {
  if(!key)throw new Error(storageMessage);
  try {const value=localStorage.getItem(key);return value===null?null:recordSchema.parse(JSON.parse(value));}
  catch {throw new Error(storageMessage);}
}
/** Only original operation bindings and status are stored, never message text,
 * profile paths, recipients, credentials or confirmation tokens. */
export function writeNativeOutreachRecord(key:string|null,record:NativeOutreachRecord|null,expected?:NativeOutreachBinding):void {
  if(!key)throw new Error(storageMessage);
  try {
    const current=readNativeOutreachRecord(key);
    if(expected && current && JSON.stringify(current.binding)!==JSON.stringify(expected))throw new Error();
    if(!expected && current)throw new Error();
    const bytes=record?JSON.stringify(recordSchema.parse(record)):null;
    if(bytes===null)localStorage.removeItem(key);else localStorage.setItem(key,bytes);
    if(localStorage.getItem(key)!==bytes)throw new Error();
    window.dispatchEvent(new Event(event));
  }catch {throw new Error(storageMessage);}
}
export function useNativeOutreachRecord(key:string|null) {
  const [,refresh]=useReducer(value=>value+1,0);
  useEffect(()=>{
    const update=()=>refresh();window.addEventListener(event,update);window.addEventListener('storage',update);
    return ()=>{window.removeEventListener(event,update);window.removeEventListener('storage',update);};
  },[]);
  try {return {record:readNativeOutreachRecord(key),error:''};}
  catch {return {record:null,error:storageMessage};}
}
