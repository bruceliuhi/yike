import {expect, it} from 'vitest';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const flowId = '00000000-0000-4000-8000-000000000001';
const row = {connection_id: flowId, device_id: 'device-1', account_public_id: '66c01234abcdef0123456789',
  platform: 'XIAOHONGSHU', status: 'CONNECTED', connection_version: 1,
  connected_at: '2026-09-10T00:00:00Z', disconnected_at: null};
async function api() {
  expect(existsSync(fileURLToPath(new URL('../src/shared/platformConnection.ts', import.meta.url)))).toBe(true);
  return import('../src/shared/platformConnection');
}
it('fixed commands accept only platform and opaque flow control', async () => {
  const {platformConnectionCommandSchema: schema, PLATFORM_CONNECTION_CHANNEL} = await api();
  expect(PLATFORM_CONNECTION_CHANNEL).toBe('desktop:platform-connection-command');
  for (const action of ['OPEN', 'CHECK', 'CANCEL']) {
    const value = {action, platform: 'XIAOHONGSHU', ...(action === 'OPEN' ? {} : {flowId})};
    expect(schema.parse(value)).toEqual(value);
    for (const extra of [{path: 'private'}, {accountId: 'fake'}, {status: 'CONNECTED'}, {device_id: 'fake'}])
      expect(schema.safeParse({...value, ...extra}).success).toBe(false);
  }
  expect(schema.safeParse({action: 'CHECK', platform: 'XIAOHONGSHU'}).success).toBe(false);
  for (const platform of ['XIAOHONGSHU', 'DOUYIN', 'BILIBILI'])
    expect(schema.safeParse({action: 'OPEN', platform}).success).toBe(true);
  expect(schema.safeParse({action: 'OPEN', platform: 'ZHIHU'}).success).toBe(false);
});
it('strict results never carry private material or upgrade other rows into a new connection', async () => {
  const {platformConnectionResultSchema: schema, connectionRegistryRowSchema} = await api();
  expect(schema.parse({state: 'CONNECTED', flowId, connection: row})).toEqual({state: 'CONNECTED', flowId, connection: row});
  expect(connectionRegistryRowSchema.safeParse({...row, platform: 'DOUYIN'}).success).toBe(true);
  for (const change of [{status: 'UNVERIFIED'}, {cookie: 'private'}])
    expect(schema.safeParse({state: 'CONNECTED', flowId, connection: {...row, ...change}}).success).toBe(false);
  for (const platform of ['DOUYIN', 'BILIBILI'])
    expect(schema.safeParse({state: 'CONNECTED', flowId, connection: {...row, platform}}).success).toBe(true);
  for (const state of ['OPENED', 'WAITING_LOGIN', 'UNKNOWN', 'CANCELLED'])
    expect(schema.safeParse({state, flowId}).success).toBe(true);
  expect(schema.safeParse({state: 'FAILED', error: 'SOURCE_STOP_FAILED'}).success).toBe(true);
  expect(schema.safeParse({state: 'FAILED', error: 'private error'}).success).toBe(false);
  expect(schema.safeParse({state: 'OPENED', flowId, path: 'private'}).success).toBe(false);
});
