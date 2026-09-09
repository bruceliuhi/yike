import {describe, expect, it} from 'vitest';
import {validatedOperation, validatedExternalUrl, validClipboardText} from '../src/main/servicePolicy';
import {configuredService} from '../src/main/serviceClient';

describe('desktop service boundary', () => {
  it('only allows a configured HTTPS origin, with explicit unpackaged loopback HTTP', () => {
    const prod = {packaged: true, allowLoopbackHttp: true};
    expect(configuredService('https://customer.example:8443', prod)).toBe('https://customer.example:8443');
    for (const input of ['http://127.0.0.1:8000', 'https://user:secret@example.com', 'https://example.com/api', 'https://example.com?token=x', 'file:///tmp/app', 'https://example.com\\@evil']) {
      expect(configuredService(input, prod)).toBeNull();
    }
    expect(configuredService('http://127.0.0.1:8000', {packaged: false, allowLoopbackHttp: true})).toBe('http://127.0.0.1:8000');
    expect(configuredService('http://localhost.evil', {packaged: false, allowLoopbackHttp: true})).toBeNull();
    expect(configuredService('http://localhost:8000', {packaged: false, allowLoopbackHttp: false})).toBeNull();
  });

  it('maps only fixed operations and validates payload fields and lengths', () => {
    expect(validatedOperation({operation: 'profiles.confirm', payload: {version_id: 'v1-demo'}})).toMatchObject({path: '/api/ui/profiles/v1-demo/confirm', method: 'POST'});
    expect(validatedOperation({operation: 'capabilities.get'})).toMatchObject({path: '/api/ui/capabilities', method: 'GET'});
    for (const request of [
      {operation: 'fetch', payload: {url: 'https://evil'}},
      {operation: 'session.get', url: 'https://evil'},
      {operation: 'session.get', payload: {headers: {Authorization: 'secret'}}},
      {operation: 'profiles.save', payload: {description: '   '}},
      {operation: 'profiles.save', payload: {description: 'a'.repeat(8001)}},
      {operation: 'profiles.confirm', payload: {version_id: '../session'}},
      {operation: 'opportunities.get', payload: {id: '%2e%2e%2fadmin'}},
      {operation: 'followups.add', payload: {opportunity_id: 'opp1', status: 'SENT', note: 'no'}},
      {operation: 'session.login', payload: {token: 'token', tenant_id: 'other'}}
    ]) expect(validatedOperation(request)).toBeNull();
  });

  it('opens only explicit HTTP(S) source URLs and bounds clipboard text', () => {
    expect(validatedExternalUrl('https://example.com/source?q=1')).toBe('https://example.com/source?q=1');
    for (const url of ['file:///tmp/private', 'javascript:alert(1)', 'yike://app/index.html', 'https://user:pass@example.com', 'https://example.com\n', '//example.com']) expect(validatedExternalUrl(url)).toBeNull();
    expect(validClipboardText('询价草稿')).toBe(true);
    for (const value of ['', 'a'.repeat(20001), 'a\0b', 1, {}]) expect(validClipboardText(value)).toBe(false);
  });
});
