import {expect, it} from 'vitest';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {parseExecutionReceipt} from '../src/shared/executionReceipt';
const id = (n:number) => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const request = {schema_version:'execution-runtime-v1',request_id:id(1),operation:'STOP',device_id:id(2),
  credential_version:1,task_id:id(3),platform_run_id:id(4),lease_id:id(5),execution_generation:1};
const receipt = {schema_version:'execution-runtime-v1',request_id:id(1),operation:'STOP',task_id:id(3),run_id:id(6),
  platform_run_id:id(4),lease_id:id(5),execution_generation:1,status:'CANCELED',stop_confirmed:true};
it('accepts exact stopped platform acknowledgements and partial cancellation',()=>{
  const parsed=executionOperationSchema.parse(request);
  expect(Object.hasOwn(parsed,'upload_request_id')).toBe(false);
  expect(parseExecutionReceipt(receipt,parsed)).toEqual(receipt);
  expect(parseExecutionReceipt({...receipt,status:'CANCELLING',stop_confirmed:false},parsed)).toMatchObject({stop_confirmed:false});
});
it.each(['platform_run_id','lease_id','execution_generation'])('rejects STOP receipt with wrong %s',field=>{
  const parsed=executionOperationSchema.parse(request);
  expect(()=>parseExecutionReceipt({...receipt,[field]:field==='execution_generation'?2:id(9)},parsed)).toThrow('EXECUTION_RECEIPT_INVALID');
});
it('rejects missing stop binding, upload attachment and contradictory terminal state',()=>{
  expect(executionOperationSchema.safeParse({...request,lease_id:null}).success).toBe(false);
  expect(executionOperationSchema.safeParse({...request,upload_request_id:'batch'}).success).toBe(false);
  expect(executionOperationSchema.safeParse({...request,upload_request_id:null}).success).toBe(false);
  expect(()=>parseExecutionReceipt({...receipt,stop_confirmed:false},executionOperationSchema.parse(request))).toThrow();
});
