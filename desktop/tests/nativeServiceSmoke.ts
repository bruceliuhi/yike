// Native Electron transport test; fixtures below are not customer data or product capabilities.
import {app, session} from 'electron';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createServiceClient, configuredService} from '../src/main/serviceClient';

if (process.env.YIKE_NATIVE_SMOKE_USER_DATA) app.setPath('userData', process.env.YIKE_NATIVE_SMOKE_USER_DATA);

async function run(): Promise<void> {
  await app.whenReady();
  let origin = '';
  let redirectsFollowed = 0;
  const server = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'application/json');
    if (request.url === '/redirect-target') { redirectsFollowed++; response.end('{}'); return; }
    if (request.headers.origin !== origin) { response.writeHead(403); response.end('{"detail":{"code":"origin_forbidden"}}'); return; }
    if (request.url === '/api/ui/capabilities') { response.writeHead(302, {Location: origin + '/redirect-target'}); response.end('{}'); return; }
    if (request.method === 'POST') response.setHeader('Set-Cookie', 'native_test_session=fixture; Path=/; HttpOnly; SameSite=Lax');
    if (request.method === 'DELETE') response.setHeader('Set-Cookie', 'native_test_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0');
    response.end(JSON.stringify({authenticated: request.method === 'POST' || Boolean(request.headers.cookie?.includes('native_test_session=fixture'))}));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  assert(address && typeof address !== 'string');
  origin = `http://127.0.0.1:${address.port}`;
  const isolated = session.fromPartition('yike-native-smoke');
  const outsider = session.fromPartition('yike-native-smoke-other');
  try {
    const baseUrl = configuredService(origin, {packaged: false, allowLoopbackHttp: true});
    assert.equal(baseUrl, origin);
    assert.equal(configuredService(origin, {packaged: true, allowLoopbackHttp: true}), null);
    const client = createServiceClient({baseUrl, fetch: (url, init) => isolated.fetch(url, init), clearSession: () => isolated.clearStorageData()});
    assert.deepEqual(await client.request({operation: 'session.login', payload: {token: 'native-test-fixture'}}), {ok: true, status: 200, data: {authenticated: true}});
    assert.equal((await isolated.cookies.get({url: origin})).length, 1, 'Login cookie should be stored in the isolated memory session.');
    assert.deepEqual(await client.request({operation: 'session.get'}), {ok: true, status: 200, data: {authenticated: true}});
    const outside = await outsider.fetch(origin + '/api/ui/session', {headers: {Origin: origin}, credentials: 'include'});
    assert.deepEqual(await outside.json(), {authenticated: false}, 'Other sessions must not share authentication.');
    const redirect = await client.request({operation: 'capabilities.get'});
    assert.equal(redirect.ok, false, 'Redirect must never resolve as a successful API operation.');
    // Electron 43 rejects manual redirects as a fetch network error; other runtimes expose the 3xx response.
    assert(!redirect.ok && ['SERVICE_REDIRECT_REJECTED', 'SERVICE_UNAVAILABLE'].includes(redirect.error));
    assert.equal(redirectsFollowed, 0, 'Service redirects must not be followed.');
    assert.equal((await client.request({operation: 'session.logout'})).ok, true);
    assert.equal((await isolated.cookies.get({url: origin})).length, 0, 'Logout must clear local session cookies.');
    assert.deepEqual(await client.request({operation: 'session.get'}), {ok: true, status: 200, data: {authenticated: false}});
    console.log('PASS native Electron transport: actual Origin, memory cookie roundtrip, session isolation, redirect rejection, logout clearing.');
  } finally {
    await isolated.clearStorageData();
    await outsider.clearStorageData();
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
}

void run().then(() => app.exit(0), error => {
  console.error(error instanceof Error ? error.message : 'NATIVE_SERVICE_SMOKE_FAILED');
  app.exit(1);
});
