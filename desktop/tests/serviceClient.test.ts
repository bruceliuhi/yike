import {describe, expect, it, vi} from 'vitest';
import {createServiceClient} from '../src/main/serviceClient';

describe('fixed service transport', () => {
  it('does not request anything without service config or with an invalid operation', async () => {
    const fetch = vi.fn();
    const client = createServiceClient({baseUrl: null, fetch, clearSession: async () => {}});
    expect(await client.request({operation: 'profiles.list'})).toMatchObject({ok: false, error: 'SERVICE_NOT_CONFIGURED'});
    expect(await client.request({operation: 'arbitrary.url'})).toMatchObject({ok: false, error: 'INVALID_API_REQUEST'});
    expect(fetch).not.toHaveBeenCalled();
  });

  it('uses the fixed origin, session cookies and no renderer-supplied headers', async () => {
    const fetch = vi.fn(async () => Response.json({items: []}));
    const client = createServiceClient({baseUrl: 'https://customer.example', fetch, clearSession: async () => {}});
    expect(await client.request({operation: 'profiles.list'})).toEqual({ok: true, status: 200, data: {items: []}});
    expect(fetch).toHaveBeenCalledWith('https://customer.example/api/ui/profiles', expect.objectContaining({
      method: 'GET', credentials: 'include', redirect: 'manual',
      headers: {Accept: 'application/json', Origin: 'https://customer.example'}
    }));
  });

  it('rejects redirects, HTML, oversized streams and surfaces only safe error codes', async () => {
    const responses = [
      new Response('', {status: 302, headers: {Location: 'https://evil'}}),
      new Response('<html>error</html>', {headers: {'Content-Type': 'text/html'}}),
      Response.json({content: 'x'.repeat(100)}),
      Response.json({detail: {code: 'origin_forbidden', message: '/private/path'}}, {status: 403})
    ];
    const client = createServiceClient({baseUrl: 'https://customer.example', fetch: async () => responses.shift()!, clearSession: async () => {}, maxResponseBytes: 90});
    expect(await client.request({operation: 'session.get'})).toMatchObject({error: 'SERVICE_REDIRECT_REJECTED'});
    expect(await client.request({operation: 'session.get'})).toMatchObject({error: 'SERVICE_NON_JSON_RESPONSE'});
    expect(await client.request({operation: 'session.get'})).toMatchObject({error: 'SERVICE_RESPONSE_TOO_LARGE'});
    expect(await client.request({operation: 'session.get'})).toEqual({ok: false, status: 403, error: 'origin_forbidden'});
  });

  it('orders login before logout and clears local credentials even when logout fails', async () => {
    const order: string[] = [];
    let release!: () => void;
    const pending = new Promise<void>(resolve => {release = resolve;});
    const client = createServiceClient({
      baseUrl: 'https://customer.example',
      fetch: async (_url, init) => {
        order.push(init.method!);
        if (init.method === 'POST') {await pending; return Response.json({authenticated: true});}
        throw new Error('offline');
      },
      clearSession: async () => {order.push('clear');}
    });
    const login = client.request({operation: 'session.login', payload: {token: 'short-lived-token'}});
    const logout = client.request({operation: 'session.logout'});
    await Promise.resolve(); expect(order).toEqual(['POST']);
    release(); await login;
    expect(await logout).toMatchObject({ok: false, error: 'SERVICE_UNAVAILABLE'});
    expect(order).toEqual(['POST', 'DELETE', 'clear']);
  });
});
