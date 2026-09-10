import {z} from 'zod';
import type {DeviceWorkerScope} from './deviceIdentityController';
import type {createConnectionProfileStore} from './connectionProfileStore';
import {connectionOperationSchema,parseConnectionReceipt} from '../shared/connectionOperation';
import {connectionRegistryRowSchema} from '../shared/platformConnection';
import {deviceUuidSchema} from '../shared/deviceRegistration';
const targetSchema=z.object({platform:z.literal('XIAOHONGSHU'),access_mode:z.literal('PLATFORM_ACCOUNT'),
  connection_id:deviceUuidSchema,connection_version:z.number().int().min(1).max(2147483647)}).strict();
const currentSchema=z.object({items:z.array(connectionRegistryRowSchema).max(10000)}).strict();
export async function resolveCollectionAccount({serviceOrigin,scope,store,target:raw}: {
  serviceOrigin:string;scope:DeviceWorkerScope;store:Pick<ReturnType<typeof createConnectionProfileStore>,'read'>;target:unknown;
}):Promise<{profileId:string;accountPublicId:string}> {
  const fail=()=>new Error('COLLECTION_ACCOUNT_UNAVAILABLE');
  const guard=()=>{if(!scope.session.isCurrent())throw fail();};
  try {
    guard();const target=targetSchema.parse(raw);
    const expectedScope={serviceOrigin,userId:scope.session.userId,deviceId:scope.device.deviceId,platform:'XIAOHONGSHU' as const};
    const record=await store.read(expectedScope);guard();
    if(!record || record.state!=='RESOLVED' || Object.entries(expectedScope).some(([k,v])=>record.scope[k as keyof typeof expectedScope]!==v))throw fail();
    const profileId=deviceUuidSchema.parse(record.profileId),verify=connectionOperationSchema.parse(record.verification);
    if(verify.action!=='VERIFY' || verify.device_id!==scope.device.deviceId || verify.platform!==target.platform || verify.connection_id!==target.connection_id ||
      verify.session_ref!==`vault://platform/${profileId}` || !/^[A-Za-z0-9]{8,32}$/.test(verify.account_public_id??''))throw fail();
    const response=await scope.transport.requestConnection({operation:'connections.receipt',payload:{request_id:verify.request_id}});guard();
    if(!response.ok)throw fail();const receipt=parseConnectionReceipt(response.data,verify);
    if(receipt.state!=='SUCCEEDED' || receipt.connection_version!==target.connection_version)throw fail();
    const current=await scope.transport.requestConnection({operation:'connections.current'});guard();
    if(!current.ok)throw fail();const rows=currentSchema.parse(current.data).items;
    if(new Set(rows.map(r=>r.connection_id)).size!==rows.length || !rows.some(r=>r.connection_id===target.connection_id &&
      r.device_id===scope.device.deviceId && r.platform===target.platform && r.account_public_id===verify.account_public_id &&
      r.status==='CONNECTED' && r.connection_version===target.connection_version))throw fail();
    return {profileId,accountPublicId:verify.account_public_id!};
  } catch {throw fail();}
}
