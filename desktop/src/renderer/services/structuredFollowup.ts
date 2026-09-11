import type {ApiOperation} from '../../shared/contracts';
import {followupWireBinding,followupMutationWire,followupRepliesWire} from '../../shared/structuredFollowup';
import {readSnapshot,readReplies,readReceipt} from '../domain/followup';
import type {Session} from '../domain/models';
import type {FollowupService} from './followup';
type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown)=>Promise<unknown>;
const key=(s:Session)=>JSON.stringify([s.authenticated,s.userId,s.accountScope?.id,s.accountScope?.version]);
export function createStructuredFollowupService(transport:Transport,session:()=>Promise<Session>):FollowupService{
 async function active(){const s=await session();if(!s.authenticated||!s.userId||!s.accountScope)throw new Error('请在已核实的客户空间中查看跟进。');return s;}
 async function call<T>(op:ApiOperation,path:string,method:string,payload:unknown,read:(raw:unknown)=>T):Promise<T>{
  const before=await active();
  if(key(await active())!==key(before))throw new Error('账户已变化，未提交跟进操作。');
  const result=read(await transport(op,path,method,payload));
  if(key(await active())!==key(before))throw new Error('账户已变化，请回原空间核对原请求。');
  return result;
 }
 return {
  list:()=>call('followup.list','/followup-workspace','GET',{},readSnapshot),
  replies:(opportunityId)=>{const query=followupRepliesWire.parse(opportunityId?{opportunityId}:{});
   return call('followup.replies',`/followup-workspace/replies${query.opportunityId?`?opportunityId=${encodeURIComponent(query.opportunityId)}`:''}`,'GET',query,raw=>readReplies(raw,query.opportunityId));},
  mutate:(raw)=>{const value=followupMutationWire.parse(raw);
   return call('followup.mutate','/followup-workspace/mutate','POST',value,raw=>readReceipt(raw,value.binding));},
  operation:(raw)=>{const value=followupWireBinding.parse(raw);
   return call('followup.operation','/followup-workspace/operation','POST',value,raw=>readReceipt(raw,value));},
 };
}
