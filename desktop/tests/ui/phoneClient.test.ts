// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {service} from '../../src/renderer/services/client';
import type {YikeDesktopApi} from '../../src/shared/contracts';

const host = window as unknown as {yikeDesktop?: YikeDesktopApi};
afterEach(() => { delete host.yikeDesktop; vi.unstubAllGlobals(); });

function bridge(data: unknown) {
  const requestApi = vi.fn().mockResolvedValue({ok: true, status: 200, data});
  host.yikeDesktop = {requestApi} as unknown as YikeDesktopApi;
  return requestApi;
}

describe('phone login fixed transport', () => {
  it('maps code cooldown without asserting message delivery', async () => {
    const call = bridge({retry_after: 60});
    await expect(service.requestCode('19900000001')).resolves.toEqual({retryAfter: 60});
    expect(call).toHaveBeenCalledWith({operation: 'session.requestCode', payload: {phone: '19900000001'}});
  });
  it('exchanges phone proof without exposing a token', async () => {
    const call = bridge({authenticated: true, user_id: 'test-user'});
    await expect(service.login('19900000001', '123456', 'invitation')).resolves.toEqual({authenticated: true, userId: 'test-user'});
    expect(call).toHaveBeenCalledWith({operation: 'session.loginPhone', payload: {phone: '19900000001', code: '123456', trial_code: 'invitation'}});
  });
  it('omits unused trial field but preserves explicitly supplied code', async () => {
    const call = bridge({authenticated: true, user_id: 'test-user'});
    await service.login('19900000001', '123456');
    expect(call).toHaveBeenCalledWith({operation: 'session.loginPhone', payload: {phone: '19900000001', code: '123456'}});
  });
  it.each([{}, {retry_after: '60'}, {retry_after: -1}, {retry_after: 0}, {retry_after: 301}, {retry_after: 1.5}])(
    'rejects malformed cooldown %j', async data => {
      bridge(data);
      await expect(service.requestCode('19900000001')).rejects.toMatchObject({code: 'INVALID_SERVICE_RESPONSE'});
    });
  it.each([{}, {authenticated: true}, {authenticated: true, user_id: ' '}, {authenticated: 'true', user_id: 'test-user'}])(
    'rejects malformed session %j', async data => {
      bridge(data);
      await expect(service.login('19900000001', '123456')).rejects.toMatchObject({code: 'INVALID_SERVICE_RESPONSE'});
    });
  it('preserves disabled service status', async () => {
    host.yikeDesktop = {requestApi: vi.fn().mockResolvedValue({ok: false, status: 501, error: 'capability_unavailable'})} as unknown as YikeDesktopApi;
    await expect(service.requestCode('19900000001')).rejects.toMatchObject({status: 501});
    await expect(service.login('19900000001', '123456')).rejects.toMatchObject({status: 501});
  });
});
