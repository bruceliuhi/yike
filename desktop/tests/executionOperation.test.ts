import {describe, expect, it} from 'vitest';
import {executionOperationSchema, executionSignatureSchema} from '../src/shared/executionOperation';

const uuid = 'abcdef01-2345-6789-abcd-ef0123456789';
const base = {schema_version: 'execution-runtime-v1', request_id: uuid, device_id: uuid, credential_version: 1};
const anonymous = {platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null};
const account = {platform: 'BILIBILI', access_mode: 'PLATFORM_ACCOUNT', connection_id: uuid, connection_version: 1};
const conditional = ['profile_version_id', 'strategy_version_id', 'configuration_sha256', 'targets',
  'task_id', 'platform_run_id', 'lease_id', 'execution_generation'] as const;
const applicable = {
  START: {profile_version_id: 'profile-1', strategy_version_id: 'strategy-1', configuration_sha256: 'a'.repeat(64), targets: [anonymous]},
  CLAIM: {task_id: 'task-1', platform_run_id: 'run-1'},
  RENEW: {task_id: 'task-1', platform_run_id: 'run-1', lease_id: 'lease-1', execution_generation: 1},
  CANCEL: {task_id: 'task-1'},
};
const start = {...base, operation: 'START', ...applicable.START};

describe('strict execution operation', () => {
  it.each(Object.entries(applicable))('normalizes omitted conditional fields to null for %s', (operation, fields) => {
    const parsed = executionOperationSchema.parse({...base, operation, ...fields});
    const expected = {...Object.fromEntries(conditional.map(key => [key, null])), ...base, operation, ...fields};
    if (operation === 'START') Object.assign(expected, {targets: [{...anonymous, connection_version: null}]});
    expect(parsed).toEqual(expected);
    expect(Object.keys(parsed)).toHaveLength(13);
    expect(executionOperationSchema.parse(parsed)).toEqual(parsed);
  });

  for (const [operation, fields] of Object.entries(applicable)) {
    it.each(conditional)(`${operation} enforces applicability of %s`, key => {
      const body: Record<string, unknown> = {...base, operation, ...fields};
      if (Object.hasOwn(fields, key)) {
        delete body[key];
        expect(executionOperationSchema.safeParse(body).success).toBe(false);
        expect(executionOperationSchema.safeParse({...body, [key]: null}).success).toBe(false);
      } else {
        const values = {...applicable.START, ...applicable.RENEW};
        expect(executionOperationSchema.safeParse({...body, [key]: values[key as keyof typeof values]}).success).toBe(false);
        expect(executionOperationSchema.safeParse({...body, [key]: null}).success).toBe(true);
      }
    });
  }

  it.each([
    null, [], 'request', {}, {...start, schema_version: 'v1'}, {...start, operation: 'STOP'},
    {...start, user_id: 'other'}, {...start, tenant_id: 'other'}, {...start, signature: 'secret'},
    {...start, request_id: uuid.toUpperCase()}, {...start, device_id: uuid.toUpperCase()},
    {...start, request_id: uuid + '\n'}, {...start, device_id: '../device'},
    {...start, configuration_sha256: 'A'.repeat(64)}, {...start, configuration_sha256: 'a'.repeat(64) + '\n'},
    {...start, configuration_sha256: 'g'.repeat(64)}, {...start, targets: []},
    {...start, targets: [anonymous, anonymous]}, {...start, targets: 'PUBLIC_WEB'},
  ])('rejects malformed or unknown input %#', value => {
    expect(executionOperationSchema.safeParse(value).success).toBe(false);
  });

  it.each(['schema_version', 'request_id', 'device_id', 'credential_version', 'operation'])('requires common field %s', field => {
    const input: Record<string, unknown> = {...start};
    delete input[field];
    expect(executionOperationSchema.safeParse(input).success).toBe(false);
  });

  it.each(['profile_version_id', 'strategy_version_id', 'task_id', 'platform_run_id', 'lease_id'])('enforces opaque ASCII grammar and bounds on %s', field => {
    const body = field === 'profile_version_id' || field === 'strategy_version_id' ? start
      : {...base, operation: 'RENEW', ...applicable.RENEW};
    for (const valid of ['a', '0', 'Z_:.9-' + 'a'.repeat(122)]) {
      expect(executionOperationSchema.safeParse({...body, [field]: valid}).success).toBe(true);
    }
    for (const invalid of ['', 'a'.repeat(129), '-leading', '.leading', '_leading', ':leading',
      ' spaced', 'trailing ', 'a\n', 'a\r', 'a\0', '中文', 'a/b', 'a@b', 1, false]) {
      expect(executionOperationSchema.safeParse({...body, [field]: invalid}).success).toBe(false);
    }
  });

  it.each(['credential_version', 'execution_generation', 'connection_version'])('bounds strict integer %s', field => {
    const input = (value: unknown) => field === 'execution_generation'
      ? {...base, operation: 'RENEW', ...applicable.RENEW, execution_generation: value}
      : field === 'connection_version' ? {...start, targets: [{...account, connection_version: value}]}
        : {...start, credential_version: value};
    for (const valid of [1, 2_147_483_647]) expect(executionOperationSchema.safeParse(input(valid)).success).toBe(true);
    for (const invalid of [0, -1, 1.1, 2_147_483_648, Number.MAX_SAFE_INTEGER, Infinity, NaN, '1', true, null]) {
      expect(executionOperationSchema.safeParse(input(invalid)).success).toBe(false);
    }
  });

  it('preserves all five unique platform targets in original order and clones nested input', () => {
    const targets = ['ZHIHU', 'BILIBILI', 'DOUYIN', 'XIAOHONGSHU', 'PUBLIC_WEB'].map(platform => ({...account, platform}));
    const parsed = executionOperationSchema.parse({...start, targets});
    expect(parsed.targets).toEqual(targets);
    targets[0].connection_version = 2;
    expect(parsed.targets![0].connection_version).toBe(1);
    expect(executionOperationSchema.safeParse({...start, targets: [...targets, anonymous]}).success).toBe(false);
  });

  it.each([
    {...anonymous, platform: 'BILIBILI'}, {...anonymous, connection_id: uuid}, {...anonymous, connection_version: 1},
    {...account, connection_id: null}, {...account, connection_version: null}, {...account, connection_id: uuid.toUpperCase()},
    {...account, connection_id: uuid + '\n'}, {...account, platform: 'OTHER'}, {...account, access_mode: 'PUBLIC'},
    {...account, session_ref: 'secret'}, {...anonymous, session_ref: 'secret'}, null, [],
    {platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS'},
    {platform: 'BILIBILI', access_mode: 'PLATFORM_ACCOUNT', connection_id: uuid},
  ])('rejects target contract violation %#', target => {
    expect(executionOperationSchema.safeParse({...start, targets: [target]}).success).toBe(false);
  });
});

describe('canonical Ed25519 execution signature', () => {
  it.each(['A', 'Q', 'g', 'w'])('accepts canonical final sextet %s', final => {
    const value = 'A'.repeat(85) + final;
    expect(executionSignatureSchema.parse(value)).toBe(value);
  });
  it.each([null, 1, '', 'A'.repeat(85), 'A'.repeat(87), 'A'.repeat(85) + 'B', 'A'.repeat(85) + '_',
    'A'.repeat(86) + '==', 'A'.repeat(85) + '+', 'A'.repeat(85) + '/', 'A'.repeat(86) + '\n'])('rejects malformed signature %#', value => {
    expect(executionSignatureSchema.safeParse(value).success).toBe(false);
  });
});
