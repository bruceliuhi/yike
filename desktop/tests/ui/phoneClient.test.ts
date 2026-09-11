// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {service} from '../../src/renderer/services/client';
import type {YikeDesktopApi} from '../../src/shared/contracts';
import {validatedOperation} from '../../src/main/servicePolicy';

const host = window as unknown as {yikeDesktop?: YikeDesktopApi};
afterEach(() => { delete host.yikeDesktop; vi.unstubAllGlobals(); });

function bridge(data: unknown) {
  const requestApi = vi.fn().mockResolvedValue({ok: true, status: 200, data});
  host.yikeDesktop = {requestApi} as unknown as YikeDesktopApi;
  return requestApi;
}

describe('phone login fixed transport', () => {
  it('uses a separate bounded temporary access endpoint without phone or token exposure', async () => {
    const call=bridge({authenticated:true,user_id:'test-access-user'});
    await expect(service.loginAccess!('YKA-synthetic-only')).resolves.toEqual({authenticated:true,userId:'test-access-user'});
    expect(call).toHaveBeenCalledWith({operation:'session.loginAccess',payload:{access_code:'YKA-synthetic-only'}});
    expect(validatedOperation({operation:'session.loginAccess',payload:{access_code:'YKA-synthetic-only'}})).toMatchObject({
      path:'/api/ui/auth/access-session',method:'POST',body:JSON.stringify({access_code:'YKA-synthetic-only'})});
    for(const payload of [{access_code:''},{access_code:'x'.repeat(129)},{access_code:'test',phone:'19900000001'}])
      expect(validatedOperation({operation:'session.loginAccess',payload})).toBeNull();
  });
  it('explains invalid temporary credentials and rejects an unverified login response',async()=>{
    host.yikeDesktop={requestApi:vi.fn().mockResolvedValue({ok:false,status:401,error:'access_auth_failed'})} as unknown as YikeDesktopApi;
    await expect(service.loginAccess!('YKA-synthetic')).rejects.toThrow('临时访问码无效、已到期或已停用，请联系管理员核对。');
    bridge({authenticated:true});
    await expect(service.loginAccess!('YKA-synthetic')).rejects.toMatchObject({code:'INVALID_SERVICE_RESPONSE'});
  });
  it.each([
    ['trial_required', '请展开试用开通，输入管理员发给你的试用码。'],
    ['trial_invalid', '试用码无效或不属于此手机号，请核对管理员发放的信息。'],
    ['trial_expired', '试用已到期或已停用，请联系管理员。'],
    ['trial_already_used', '该账号已激活，请收起试用开通后使用短信验证码登录。'],
  ])('explains trial decision %s without treating it as an unrelated permission error', async (code, message) => {
    host.yikeDesktop = {requestApi: vi.fn().mockResolvedValue({ok: false, status: 403, error: code})} as unknown as YikeDesktopApi;
    await expect(service.login('19900000001', '123456', 'invitation')).rejects.toMatchObject({code, message});
  });
  it('explains rejected access credentials without changing ordinary session errors', async () => {
    host.yikeDesktop = {requestApi: vi.fn().mockResolvedValue({ok: false, status: 401, error: 'authentication_required'})} as unknown as YikeDesktopApi;
    await expect(service.loginToken('invalid-uat-credential')).rejects.toMatchObject({
      code: 'authentication_required', status: 401,
      message: '访问凭证无效或已过期，请核对或向服务方获取新的短期凭证。',
    });
    await expect(service.session()).rejects.toThrow('请先登录，再访问客户工作空间。');
  });
  it('does not describe network failures as invalid credentials', async () => {
    host.yikeDesktop = {requestApi: vi.fn().mockResolvedValue({ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'})} as unknown as YikeDesktopApi;
    await expect(service.loginToken('invalid-uat-credential')).rejects.toThrow('客户服务暂时不可用，请稍后重试。');
  });
  it('shows an actionable phone-proof error on the login page', async () => {
    host.yikeDesktop = {requestApi: vi.fn().mockResolvedValue({ok: false, status: 401, error: 'phone_auth_failed'})} as unknown as YikeDesktopApi;
    await expect(service.login('19900000001', '123456')).rejects.toThrow('验证码无效或已过期，请重新核对或获取验证码。');
  });
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
