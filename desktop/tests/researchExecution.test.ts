import {describe, expect, it} from 'vitest';
import {validatedExecutionOperation} from '../src/main/executionServicePolicy';
import {validatedOperation} from '../src/main/servicePolicy';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {parseResearchStartReceipt} from '../src/shared/researchExecution';

const id = (last: number) => `10000000-0000-4000-8000-${last.toString().padStart(12, '0')}`;
const request = () => executionOperationSchema.parse({
  schema_version: 'execution-runtime-v1', operation: 'START', request_id: id(1),
  device_id: id(2), credential_version: 1, profile_version_id: id(3), strategy_version_id: id(4),
  configuration_sha256: 'a'.repeat(64),
  targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null}],
});
// Synthetic token and signature: no actual credentials or external execution.
const envelope = () => ({request: request(), signature: 'A'.repeat(86), authorization_token: 'eyJ0ZXN0Ijp0cnVlfQ.AA'});
const binding = () => ({quote_id: id(6), strategy_version_id: id(4), profile_version_id: id(3),
  configuration_sha256: 'a'.repeat(64), rule_version: 'synthetic-test-rule-v1', rule_sha256: 'b'.repeat(64),
  estimated_soubei: 6, max_soubei: 10, limits: {sources: 20, minutes: 5, modelCalls: 10}});
const receipt = () => ({schema_version: 'research-execution-v1',
  execution: {schema_version: 'execution-runtime-v1', request_id: id(1), operation: 'START',
    task_id: id(5), run_id: id(7), status: 'PENDING', stop_confirmed: false,
    platform_runs: [{platform_run_id: id(8), platform: 'PUBLIC_WEB', status: 'PENDING'}]},
  reservation: {...binding(), reservation_id: id(9), status: 'RESERVED'}});

describe('main-only research START transport', () => {
  it('maps a strict research envelope to the fixed new route without changing signed request bytes', () => {
    const payload = envelope();
    const routed = validatedExecutionOperation({operation: 'researchExecution.start', payload});
    expect(routed).toEqual({path: '/api/ui/research-execution/start', method: 'POST',
      body: JSON.stringify(payload), logout: false});
    expect(JSON.parse(routed!.body!).request).toEqual(request());
    expect(JSON.parse(routed!.body!).request).not.toHaveProperty('authorization_token');
  });

  it('recovers by request ID alone without replaying authorization', () => {
    expect(validatedExecutionOperation({operation: 'researchExecution.receipt', payload: {request_id: id(1)}}))
      .toEqual({path: `/api/ui/research-execution/operations/${id(1)}`, method: 'GET', logout: false});
    expect(validatedExecutionOperation({operation: 'researchExecution.receipt',
      payload: {request_id: id(1), authorization_token: envelope().authorization_token}})).toBeNull();
  });

  it('keeps both operations out of public renderer IPC', () => {
    expect(validatedOperation({operation: 'researchExecution.start', payload: envelope()})).toBeNull();
    expect(validatedOperation({operation: 'researchExecution.receipt', payload: {request_id: id(1)}})).toBeNull();
  });

  it('rejects unknown fields, malformed signature/token and non-START operations', () => {
    const valid = envelope();
    for (const payload of [
      {...valid, extra: true}, {...valid, signature: 'A'.repeat(85)},
      {...valid, authorization_token: ''}, {...valid, authorization_token: 'a'.repeat(8193)},
      {...valid, authorization_token: 'secret\n'},
      {...valid, authorization_token: valid.authorization_token + '\n'},
      {...valid, request: {...valid.request, authorization_token: 'untrusted'}},
      {...valid, request: executionOperationSchema.parse({schema_version: 'execution-runtime-v1',
        request_id: id(1), operation: 'CANCEL', device_id: id(2), credential_version: 1, task_id: id(5)})},
    ]) expect(validatedExecutionOperation({operation: 'researchExecution.start', payload})).toBeNull();
    expect(validatedExecutionOperation({operation: 'researchExecution.start', payload: valid, url: 'https://other.test'})).toBeNull();
    expect(validatedExecutionOperation({operation: 'researchExecution.receipt', payload: {request_id: '../session'}})).toBeNull();
  });
});

describe('bound research receipt', () => {
  it('returns only the immutable START and resource reservation without authorization material', () => {
    expect(parseResearchStartReceipt(receipt(), request(), binding())).toEqual(receipt());
  });

  it.each([
    ['quote_id', id(99)], ['strategy_version_id', id(99)], ['profile_version_id', id(99)],
    ['configuration_sha256', 'c'.repeat(64)], ['rule_version', 'other-rule'],
    ['rule_sha256', 'c'.repeat(64)], ['estimated_soubei', 5], ['max_soubei', 11],
    ['limits', {sources: 21, minutes: 5, modelCalls: 10}],
    ['limits', {sources: 20, minutes: 6, modelCalls: 10}],
    ['limits', {sources: 20, minutes: 5, modelCalls: 11}],
  ])('rejects reservation mismatch for %s', (key, value) => {
    const raw = receipt();
    expect(() => parseResearchStartReceipt({...raw, reservation: {...raw.reservation, [key]: value}}, request(), binding()))
      .toThrow('RESEARCH_EXECUTION_RECEIPT_INVALID');
  });

  it('checks request identity, target order and run uniqueness with the existing execution parser', () => {
    for (const patch of [{request_id: id(99)}, {operation: 'CLAIM'},
      {platform_runs: [{platform_run_id: id(8), platform: 'DOUYIN', status: 'PENDING'}]},
      {platform_runs: [...receipt().execution.platform_runs, ...receipt().execution.platform_runs]}]) {
      expect(() => parseResearchStartReceipt({...receipt(), execution: {...receipt().execution, ...patch}}, request(), binding()))
        .toThrow('RESEARCH_EXECUTION_RECEIPT_INVALID');
    }
  });

  it('preserves multiple confirmed targets and rejects reordered or duplicated platform runs', () => {
    const twoTargets = {...request(), targets: [...request().targets!, {
      platform: 'BILIBILI', access_mode: 'PLATFORM_ACCOUNT', connection_id: id(10), connection_version: 1}]};
    const twoRuns = [...receipt().execution.platform_runs, {platform: 'BILIBILI', platform_run_id: id(11), status: 'PENDING'}];
    const raw = {...receipt(), execution: {...receipt().execution, platform_runs: twoRuns}};
    expect(parseResearchStartReceipt(raw, twoTargets, binding())).toEqual(raw);
    for (const platform_runs of [[...twoRuns].reverse(), [twoRuns[0], {...twoRuns[1], platform_run_id: id(8)}]]) {
      expect(() => parseResearchStartReceipt({...raw, execution: {...raw.execution, platform_runs}}, twoTargets, binding()))
        .toThrow('RESEARCH_EXECUTION_RECEIPT_INVALID');
    }
  });

  it('rejects even mutually agreeing receipt/binding when the signed request belongs to another strategy', () => {
    for (const patch of [{strategy_version_id: id(99)}, {profile_version_id: id(99)},
      {configuration_sha256: 'c'.repeat(64)}]) {
      expect(() => parseResearchStartReceipt(receipt(), {...request(), ...patch}, binding()))
        .toThrow('RESEARCH_EXECUTION_RECEIPT_INVALID');
    }
  });

  it('rejects invalid values even if the expectation repeats them', () => {
    for (const patch of [{rule_version: '\nsecret'}, {rule_version: 'x'.repeat(513)},
      {rule_sha256: 'b'.repeat(64) + '\n'},
      {estimated_soubei: 0}, {estimated_soubei: 6.5}, {estimated_soubei: 11}, {max_soubei: 0}, {max_soubei: 1000001},
      {limits: {sources: 0, minutes: 5, modelCalls: 10}},
      {limits: {sources: 20, minutes: 5, modelCalls: true}},
      {limits: {sources: 20, minutes: 5, modelCalls: 10, extra: 1}}]) {
      const expected = {...binding(), ...patch};
      expect(() => parseResearchStartReceipt({...receipt(), reservation: {...receipt().reservation, ...patch}}, request(), expected))
        .toThrow('RESEARCH_EXECUTION_RECEIPT_INVALID');
    }
  });

  it('fails closed on old/unknown schemas, wrong status and extra secrets at every level', () => {
    for (const raw of [receipt().execution, {...receipt(), schema_version: 'research-execution-v2'},
      {...receipt(), authorization_token: 'private'},
      {...receipt(), execution: {...receipt().execution, authorization_token: 'private'}},
      {...receipt(), reservation: {...receipt().reservation, authorization_token: 'private'}},
      {...receipt(), reservation: {...receipt().reservation, status: 'SETTLED'}}]) {
      expect(() => parseResearchStartReceipt(raw, request(), binding())).toThrow('RESEARCH_EXECUTION_RECEIPT_INVALID');
    }
  });
});
