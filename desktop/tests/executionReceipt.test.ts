import {describe, expect, it} from 'vitest';
import {executionOperationSchema, type ExecutionOperation} from '../src/shared/executionOperation';
import {parseExecutionReceipt} from '../src/shared/executionReceipt';

const requestId = 'abcdef01-2345-6789-abcd-ef0123456789';
const taskId = 'abcdef02-2345-6789-abcd-ef0123456789';
const runId = 'abcdef03-2345-6789-abcd-ef0123456789';
const platformId = 'abcdef04-2345-6789-abcd-ef0123456789';
const otherId = 'abcdef05-2345-6789-abcd-ef0123456789';
const leaseId = 'abcdef06-2345-6789-abcd-ef0123456789';
const base = {schema_version: 'execution-runtime-v1', request_id: requestId, device_id: otherId, credential_version: 1};
const start = executionOperationSchema.parse({...base, operation: 'START', profile_version_id: 'profile-1',
  strategy_version_id: 'strategy-1', configuration_sha256: 'a'.repeat(64), targets: [
    {platform: 'BILIBILI', access_mode: 'PLATFORM_ACCOUNT', connection_id: otherId, connection_version: 1},
    {platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null},
  ]});
const claim = executionOperationSchema.parse({...base, operation: 'CLAIM', task_id: taskId, platform_run_id: platformId});
const renew = executionOperationSchema.parse({...claim, operation: 'RENEW', lease_id: leaseId, execution_generation: 2});
const cancel = executionOperationSchema.parse({...base, operation: 'CANCEL', task_id: taskId});
const envelope = {schema_version: 'execution-runtime-v1', request_id: requestId, task_id: taskId, run_id: runId};
const startReceipt = {...envelope, operation: 'START', status: 'PENDING', stop_confirmed: false, platform_runs: [
  {platform_run_id: platformId, platform: 'BILIBILI', status: 'PENDING'},
  {platform_run_id: otherId, platform: 'PUBLIC_WEB', status: 'PENDING'},
]};
const claimReceipt = {...envelope, operation: 'CLAIM', status: 'RUNNING', stop_confirmed: false,
  platform_run_id: platformId, lease_id: leaseId, execution_generation: 2,
  lease_expires_at: '2020-09-10T12:00:00.000001+08:00', deadline_at: '2020-09-10T12:02:00+08:00'};
const renewReceipt = {...claimReceipt, operation: 'RENEW'};
const cancelReceipt = {...envelope, operation: 'CANCEL', status: 'CANCELED', stop_confirmed: true};
const cases = [{operation: start, receipt: startReceipt}, {operation: claim, receipt: claimReceipt},
  {operation: renew, receipt: renewReceipt}, {operation: cancel, receipt: cancelReceipt}];

function rejects(raw: unknown, expected: ExecutionOperation) {
  expect(() => parseExecutionReceipt(raw, expected)).toThrow(/^EXECUTION_RECEIPT_INVALID$/);
}

describe('strict execution receipt', () => {
  it.each(cases)('accepts exact $operation.operation receipt and snapshots it', ({operation, receipt}) => {
    const input = structuredClone(receipt);
    const parsed = parseExecutionReceipt(input, operation);
    expect(parsed).toEqual(receipt);
    expect(parsed).not.toBe(input);
  });

  for (const {operation, receipt} of cases) {
    it.each(Object.keys(receipt))(`${operation.operation} requires field %s`, key => {
      const input: Record<string, unknown> = {...receipt};
      delete input[key];
      rejects(input, operation);
    });

    it.each([
      null, [], 'receipt', {}, {...receipt, signature: 'do-not-echo-private'},
      {...receipt, schema_version: 'other'}, {...receipt, request_id: otherId},
      {...receipt, request_id: requestId.toUpperCase()}, {...receipt, request_id: requestId + '\n'},
      {...receipt, task_id: 'task-opaque'}, {...receipt, task_id: taskId.toUpperCase()},
      {...receipt, run_id: 'invalid'}, {...receipt, run_id: runId.toUpperCase()},
      {...receipt, operation: 'GET'}, {...receipt, status: 'SUCCEEDED'},
      {...receipt, stop_confirmed: 'false'}, {...receipt, stop_confirmed: 0},
    ])(`${operation.operation} rejects malformed value %#`, value => rejects(value, operation));

    it(`${operation.operation} validates expected request instead of trusting its type`, () => {
      rejects(receipt, {...operation, credential_version: 0});
      rejects(receipt, {...operation, request_id: otherId});
      rejects(receipt, {...operation, extra: 'secret'} as ExecutionOperation);
      rejects(receipt, null as unknown as ExecutionOperation);
    });
  }

  it('rejects mismatched operation even when the alternative receipt shape is valid', () => {
    rejects(claimReceipt, renew);
    rejects(renewReceipt, claim);
    rejects(startReceipt, cancel);
    rejects(cancelReceipt, start);
  });

  it.each([
    {...startReceipt, status: 'RUNNING'}, {...startReceipt, stop_confirmed: true},
    {...startReceipt, platform_runs: []}, {...startReceipt, platform_runs: startReceipt.platform_runs.slice(0, 1)},
    {...startReceipt, platform_runs: [...startReceipt.platform_runs].reverse()},
    {...startReceipt, platform_runs: startReceipt.platform_runs.map(row => ({...row, platform_run_id: platformId}))},
    {...startReceipt, platform_runs: startReceipt.platform_runs.map(row => ({...row, status: 'RUNNING'}))},
    {...startReceipt, platform_runs: startReceipt.platform_runs.map(row => ({...row, platform_run_id: 'opaque'}))},
    {...startReceipt, platform_runs: startReceipt.platform_runs.map(row => ({...row, extra: 'private'}))},
    {...startReceipt, platform_runs: [null, startReceipt.platform_runs[1]]},
    {...startReceipt, platform_runs: [{platform: 'BILIBILI', platform_run_id: platformId}, startReceipt.platform_runs[1]]},
    {...startReceipt, platform_runs: Array(6).fill(startReceipt.platform_runs[0])},
  ])('START rejects invalid platform order/shape/status %#', value => rejects(value, start));

  it('START accepts one and all five target platforms in requested order', () => {
    for (const platforms of [['PUBLIC_WEB'], ['ZHIHU', 'BILIBILI', 'DOUYIN', 'XIAOHONGSHU', 'PUBLIC_WEB']]) {
      const expected = executionOperationSchema.parse({...start, targets: platforms.map(platform => ({
        platform, access_mode: 'PLATFORM_ACCOUNT', connection_id: otherId, connection_version: 1,
      }))});
      const receipt = {...startReceipt, platform_runs: platforms.map((platform, index) => ({
        platform, platform_run_id: `abcdef0${index}-2345-6789-abcd-ef0123456789`, status: 'PENDING',
      }))};
      expect(parseExecutionReceipt(receipt, expected)).toEqual(receipt);
    }
  });

  it.each([claim, renew])('$operation matches original task/platform and running state', expected => {
    const receipt = {...claimReceipt, operation: expected.operation};
    for (const changes of [{task_id: otherId}, {platform_run_id: otherId}, {status: 'PENDING'},
      {stop_confirmed: true}, {lease_id: 'opaque'}, {lease_id: leaseId.toUpperCase()},
      {execution_generation: 0}, {execution_generation: 2_147_483_648}, {execution_generation: 1.1},
      {execution_generation: true}, {execution_generation: '2'}, {execution_generation: NaN},
      {lease_expires_at: '2020-09-10T12:03:00+08:00'}, {lease_expires_at: '2020-09-10T12:02:00.000001+08:00'},
    ]) rejects({...receipt, ...changes}, expected);
  });

  it('CLAIM accepts maximum generation while RENEW binds exact lease and generation', () => {
    expect(parseExecutionReceipt({...claimReceipt, execution_generation: 2_147_483_647}, claim)).toMatchObject({execution_generation: 2_147_483_647});
    rejects({...renewReceipt, lease_id: otherId}, renew);
    rejects({...renewReceipt, execution_generation: 1}, renew);
    expect(parseExecutionReceipt(renewReceipt, renew)).toEqual(renewReceipt);
  });

  it.each(['lease_expires_at', 'deadline_at'])('requires valid timezone ISO %s', field => {
    for (const invalid of [null, 0, '', '2020-09-10', '2020-09-10T12:00:00', '2020-02-30T12:00:00Z',
      '2020-09-10T25:00:00Z', '2020-09-10T12:00:00+24:00', '2020-09-10T12:00:00+08:99',
      '0000-01-01T00:00:00Z', '2020-09-10T12:00:00Z\n']) rejects({...claimReceipt, [field]: invalid}, claim);
  });

  it('compares instants across offsets without losing sub-millisecond precision', () => {
    const equal = {...claimReceipt, lease_expires_at: '2020-09-10T12:00:00.000001+08:00', deadline_at: '2020-09-10T04:00:00.000001Z'};
    expect(parseExecutionReceipt(equal, claim)).toEqual(equal);
    rejects({...equal, lease_expires_at: '2020-09-10T12:00:00.000002+08:00'}, claim);
    const before = {...equal, lease_expires_at: '2020-09-10T03:59:59.999999Z'};
    expect(parseExecutionReceipt(before, claim)).toEqual(before);
  });

  it('accepts historical expired leases without treating them as current authorization', () => {
    expect(parseExecutionReceipt(claimReceipt, claim)).toEqual(claimReceipt);
  });

  it('CANCEL accepts only CANCELED/true or CANCELLING/false and binds task', () => {
    const pending = {...cancelReceipt, status: 'CANCELLING', stop_confirmed: false};
    expect(parseExecutionReceipt(pending, cancel)).toEqual(pending);
    rejects({...cancelReceipt, task_id: otherId}, cancel);
    rejects({...cancelReceipt, stop_confirmed: false}, cancel);
    rejects({...pending, stop_confirmed: true}, cancel);
    rejects({...pending, status: 'CANCELED'}, cancel);
    rejects({...pending, status: 'CANCELLED'}, cancel);
    rejects({...pending, platform_runs: []}, cancel);
  });
});
