import {z} from 'zod';
import type {DeviceWorkerScope} from './deviceIdentityController';
import type {createConnectionProfileStore} from './connectionProfileStore';
import {connectionOperationSchema,parseConnectionReceipt} from '../shared/connectionOperation';
import {connectionRegistryRowSchema} from '../shared/platformConnection';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import {nativeLoginPlatformSchema,validNativeAccount} from '../shared/platformAccount';
const targetSchema=z.object({platform:nativeLoginPlatformSchema,access_mode:z.literal('PLATFORM_ACCOUNT'),
  connection_id:deviceUuidSchema,connection_version:z.number().int().min(1).max(2147483647)}).strict();
const currentSchema=z.object({items:z.array(connectionRegistryRowSchema).max(10000)}).strict();
export async function resolveCollectionAccount(input: {
  serviceOrigin:string;scope:DeviceWorkerScope;store:Pick<ReturnType<typeof createConnectionProfileStore>,'read'>;target:unknown;
  protectedRecord?:Awaited<ReturnType<ReturnType<typeof createConnectionProfileStore>['read']>>;
  currentRows?:unknown;
}):Promise<{profileId:string;accountPublicId:string}> {
  const {serviceOrigin,scope,store,target:raw}=input;
  const fail=()=>new Error('COLLECTION_ACCOUNT_UNAVAILABLE');
  const guard=()=>{if(!scope.session.isCurrent())throw fail();};
  try {
    guard();const target=targetSchema.parse(raw);
    const expectedScope={serviceOrigin,userId:scope.session.userId,deviceId:scope.device.deviceId,platform:target.platform};
    const record=input.protectedRecord??await store.read(expectedScope);guard();
    if(!record || record.state!=='RESOLVED' || Object.entries(expectedScope).some(([k,v])=>record.scope[k as keyof typeof expectedScope]!==v))throw fail();
    const profileId=deviceUuidSchema.parse(record.profileId),verify=connectionOperationSchema.parse(record.verification);
    if(verify.action!=='VERIFY' || verify.device_id!==scope.device.deviceId || verify.platform!==target.platform || verify.connection_id!==target.connection_id ||
      verify.session_ref!==`vault://platform/${profileId}` || !validNativeAccount(target.platform,verify.account_public_id??''))throw fail();
    const response=await scope.transport.requestConnection({operation:'connections.receipt',payload:{request_id:verify.request_id}});guard();
    if(!response.ok)throw fail();const receipt=parseConnectionReceipt(response.data,verify);
    if(receipt.state!=='SUCCEEDED' || receipt.connection_version!==target.connection_version)throw fail();
    let current:unknown=input.currentRows;
    if(current===undefined){const response=await scope.transport.requestConnection({operation:'connections.current'});guard();if(!response.ok)throw fail();current=response.data;}
    const rows=currentSchema.parse(current).items;
    if(new Set(rows.map(r=>r.connection_id)).size!==rows.length || !rows.some(r=>r.connection_id===target.connection_id &&
      r.device_id===scope.device.deviceId && r.platform===target.platform && r.account_public_id===verify.account_public_id &&
      r.status==='CONNECTED' && r.connection_version===target.connection_version))throw fail();
    return {profileId,accountPublicId:verify.account_public_id!};
  } catch {throw fail();}
}
