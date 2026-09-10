/** Private main-process orchestration. Not an IPC handler or a platform driver. */
import {randomUUID} from 'node:crypto';
import {z} from 'zod';
import {createOutreachConsumer,type NativeOutreachChannel,type NativeOutreachOutcome} from './outreachConsumer';
import type {OutreachConsumptionJournal} from './outreachConsumptionJournal';
import type {DeviceWorkerScope} from './deviceIdentityController';
import type {DeviceKeyMaterial,DeviceKeyScope} from './deviceKeyVault';
import {dispatchRequestSchema,type DispatchRequest} from './outreachDispatchProtocol';
import {signOutreachDispatch} from './outreachDispatchSigner';

const uuid=z.string().uuid();
const bindingSchema=z.object({tenantId:uuid,requestId:uuid,claimId:uuid,contextSha256:z.string().regex(/^[a-f0-9]{64}$/)}).strict();
type Binding=z.infer<typeof bindingSchema>;
type Scope=Pick<DeviceWorkerScope,'session'|'device'|'signal'|'close'> & {transport:Pick<DeviceWorkerScope['transport'],'requestOutreach'>};
const receiptSchema=z.object({requestId:uuid,state:z.enum(['QUEUED','UNKNOWN','SENT','FAILED','CANCELLED']),
  dispatchAllowed:z.literal(false),deliveryConfirmed:z.boolean(),claimId:uuid.optional(),
  dispatchBefore:z.string().datetime({offset:true}).optional(),resultId:uuid.optional(),
  evidenceAuthority:z.literal('DEVICE_ATTESTED_PLATFORM_RECEIPT').optional(),confirmedNotDelivered:z.literal(true).optional(),
}).strict().refine(r=>r.deliveryConfirmed===(r.state==='SENT') &&
  (r.state==='SENT'||r.state==='FAILED')===(r.evidenceAuthority!==undefined) &&
  (r.state==='FAILED')===(r.confirmedNotDelivered===true) &&
  (r.claimId!==undefined)===(r.dispatchBefore!==undefined));
type Receipt=z.infer<typeof receiptSchema>;
type Pending={state:'RESULT_PENDING';serverAccepted:false;requestId:string;claimId:string;resultId:string;outcome:NativeOutreachOutcome};
type Result={state:'UNKNOWN';serverAccepted:false;reason:string} | Pending |
  {state:'RESULT_RECORDED'|'RECONCILED';serverAccepted:true;receipt:Receipt};

export function createOutreachDispatchSession(options:{serviceOrigin:string;
  identity:{openWorkerScope():Promise<{ok:true;scope:Scope}|{ok:false;state:string}>};
  vault:{read(scope:DeviceKeyScope):Promise<DeviceKeyMaterial|null>};
  journal:OutreachConsumptionJournal;channel:NativeOutreachChannel}) {
  const unknown=(reason:string):Result=>({state:'UNKNOWN',serverAccepted:false,reason});
  async function run(raw:unknown,signal:AbortSignal,reconcile:boolean):Promise<Result>{
    const parsed=bindingSchema.safeParse(raw);if(!parsed.success)return unknown('INVALID_REQUEST');
    const binding=Object.freeze(parsed.data);let scope:Scope|undefined,pending:Pending|undefined;
    try {
      if(signal.aborted)return unknown('CANCELLED');
      const opened=await options.identity.openWorkerScope();if(!opened.ok)return unknown('DEVICE_NOT_READY');
      scope=opened.scope;
      if(!scope.signal)return unknown('DEVICE_SCOPE_UNAVAILABLE');
      // Snapshot identity and credentials so an async caller cannot retarget this action.
      const original=scope,session={...scope.session},device={...scope.device};
      const executionSignal=AbortSignal.any([signal,scope.signal]);
      const expected=Object.freeze({...binding,serviceOrigin:options.serviceOrigin,userId:session.userId,
        sessionId:session.sessionId,deviceId:device.deviceId});
      const current=()=>session.isCurrent() && !executionSignal.aborted;
      const guard=()=>{if(!current())throw new Error('SESSION_CHANGED');};
      const request=async(operation:string,payload:unknown)=>{
        guard();if(!original.transport.requestOutreach)throw new Error('TRANSPORT_UNAVAILABLE');
        const response=await original.transport.requestOutreach({operation,payload});guard();
        if(!response.ok)throw new Error('REQUEST_UNCONFIRMED');return response.data;
      };
      function receipt(rawReceipt:unknown,result?:DispatchRequest):Receipt {
        const r=receiptSchema.parse(rawReceipt);
        if(r.requestId!==binding.requestId || r.claimId!==undefined && r.claimId!==binding.claimId ||
          result && (r.claimId!==binding.claimId || r.resultId!==result.resultId || r.state!==result.outcome?.status))throw new Error('RECEIPT_MISMATCH');
        return r;
      }
      if(reconcile)return {state:'RECONCILED',serverAccepted:true,receipt:receipt(await request('outreach.dispatch.receipt',{requestId:binding.requestId}))};
      guard();const key=await options.vault.read({serviceOrigin:options.serviceOrigin,userId:session.userId,deviceId:device.deviceId});guard();
      if(!key)return unknown('DEVICE_KEY_UNAVAILABLE');
      const common={requestId:binding.requestId,claimId:binding.claimId,deviceId:device.deviceId,
        credentialVersion:device.credentialVersion,contextSha256:binding.contextSha256};
      async function signed(rawRequest:unknown){
        const value=dispatchRequestSchema.parse(rawRequest);
        const prepared=await request('outreach.dispatch.prepare',{request:value});guard();
        const signedValue=signOutreachDispatch({key:key!,prepared,expected:{serviceOrigin:options.serviceOrigin,
          userId:session.userId,tenantId:binding.tenantId,request:value}});
        return request('outreach.dispatch.apply',signedValue);
      }
      const grant=await signed({...common,action:'CLAIM'});guard();
      const consumer=createOutreachConsumer({journal:options.journal,channel:options.channel,isCurrent:()=>current()});
      const consumed=await consumer.consume(expected,grant,executionSignal);
      if(consumed.state!=='RESULT_READY')return unknown(consumed.reason);
      // Retain a valid native fact when logout, transport failure or a bad ACK prevents reporting.
      pending={state:'RESULT_PENDING',serverAccepted:false,requestId:binding.requestId,claimId:binding.claimId,resultId:randomUUID(),outcome:consumed.outcome};
      const result=dispatchRequestSchema.parse({...common,action:'RESULT',resultId:pending.resultId,outcome:pending.outcome});
      return {state:'RESULT_RECORDED',serverAccepted:true,receipt:receipt(await signed(result),result)};
    }catch{return pending ?? unknown('DISPATCH_UNCONFIRMED');}
    finally {try {scope?.close();}catch{/* No raw errors or second action on cleanup failure. */}}
  }
  return {dispatch:(binding:Binding,signal:AbortSignal)=>run(binding,signal,false),
    reconcile:(binding:Binding,signal:AbortSignal)=>run(binding,signal,true)};
}
