import {expect, it, vi} from 'vitest';
import {createServiceClient} from '../src/main/serviceClient';
it('connection reads use the same authenticated bounded queue without public exposure', async () => {
  const fetch = vi.fn(async () => new Response('{"items":[]}', {headers: {'content-type': 'application/json'}}));
  const client = createServiceClient({baseUrl: 'https://pilot.example', fetch, clearSession: async () => {}});
  expect(await (client as any).requestConnection({operation: 'connections.current'})).toMatchObject({ok: true, data: {items: []}});
  expect(fetch).toHaveBeenCalledWith('https://pilot.example/api/ui/connections', expect.objectContaining({method: 'GET', credentials: 'include', redirect: 'manual'}));
  expect(await client.request({operation: 'connections.current'})).toMatchObject({ok: false, error: 'INVALID_API_REQUEST'});
});
