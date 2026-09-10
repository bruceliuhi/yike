import {describe, expect, it} from 'vitest';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {parseExecutionReceipt} from '../src/shared/executionReceipt';

const id = '11111111-1111-4111-8111-111111111111';
const request = {schema_version:'execution-runtime-v1', request_id:id, operation:'FINISH', device_id:id,
  credential_version:1, task_id:id, platform_run_id:id, lease_id:id, execution_generation:1,
  upload_request_id:'original:batch.1'};
const receipt = {schema_version:'execution-runtime-v1', request_id:id, operation:'FINISH', task_id:id,
  run_id:id, platform_run_id:id, lease_id:id, execution_generation:1, upload_request_id:'original:batch.1',
  records_used:0, status:'SUCCEEDED', stop_confirmed:true};

describe('FINISH contract', () => {
  it('parses completed and partial historical receipts bound to the exact request', () => {
    const operation = executionOperationSchema.parse(request);
    expect(parseExecutionReceipt(receipt, operation)).toEqual(receipt);
    const partial = {...receipt, status:'RUNNING', stop_confirmed:false};
    expect(parseExecutionReceipt(partial, operation)).toEqual(partial);
  });
  it.each(['request_id','task_id','platform_run_id','lease_id','execution_generation','upload_request_id'])(
    'rejects mismatched %s', field => {
      const operation = executionOperationSchema.parse(request);
      const value = field === 'execution_generation' ? 2 : '22222222-2222-4222-8222-222222222222';
      expect(() => parseExecutionReceipt({...receipt, [field]:value}, operation)).toThrow('EXECUTION_RECEIPT_INVALID');
    });
  it('rejects contradictory stops and extra receipt data', () => {
    const operation = executionOperationSchema.parse(request);
    for (const bad of [{...receipt, stop_confirmed:false}, {...receipt, cookie:'secret'}, {...receipt, records_used:-1}]) {
      expect(() => parseExecutionReceipt(bad, operation)).toThrow('EXECUTION_RECEIPT_INVALID');
    }
  });
  it('does not add a new field to old serialized operations', () => {
    const {upload_request_id:_, ...old} = {...request, operation:'RENEW'};
    const parsed = executionOperationSchema.parse(old);
    expect(Object.hasOwn(parsed, 'upload_request_id')).toBe(false);
    expect(parsed).toEqual({...old, profile_version_id:null, strategy_version_id:null, configuration_sha256:null, targets:null});
  });
});
