import {expect, it} from 'vitest';
import {createCipheriv, createDecipheriv, createPrivateKey, createPublicKey, randomBytes, randomUUID} from 'node:crypto';
import {mkdtemp, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServiceClient} from '../../src/main/serviceClient';
import {signExecutionOperation} from '../../src/main/executionProofSigner';
import {executionOperationSchema, type ExecutionOperation} from '../../src/shared/executionOperation';
import type {ApiResult} from '../../src/shared/contracts';
import {createExecutionJournal} from '../../src/main/executionJournal';
import {createExecutionSession} from '../../src/main/executionSession';
import {createDeviceIdentityController} from '../../src/main/deviceIdentityController';
import {createExecutionController} from '../../src/main/executionController';

const names = ['BASE', 'USER', 'TOKEN', 'NEXT_TOKEN', 'SEED', 'START'] as const;
it.skipIf(!names.some(name => process.env[`YIKE_EXECUTION_LIVE_${name}`]))(
  'persists actual requests, reconstructs after lost START, leases and cancels across sessions', async () => {
    const values = Object.fromEntries(names.map(name => [name, process.env[`YIKE_EXECUTION_LIVE_${name}`]]));
    expect(Object.values(values).every(Boolean)).toBe(true);
    expect(Object.keys(process.env).filter(name => /DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
    expect(process.versions.node.split('.')[0]).toBe('24');
    const base = values.BASE!;
    expect(new URL(base).hostname).toBe('127.0.0.1');
    const start = executionOperationSchema.parse(JSON.parse(values.START!));
    const privateKey = createPrivateKey({format: 'der', type: 'pkcs8', key: Buffer.concat([
      Buffer.from('302e020100300506032b657004220420', 'hex'), Buffer.from(values.SEED!, 'hex'),
    ])});
    const key = {scope: {serviceOrigin: base, userId: values.USER!, deviceId: start.device_id},
      privateKey: privateKey.export({format: 'pem', type: 'pkcs8'}).toString(),
      publicKey: createPublicKey(privateKey).export({format: 'jwk'}).x!};
    const directory = await mkdtemp(path.join(os.tmpdir(), 'yike-execution-live-'));
    const protectionKey = randomBytes(32);
    // Test protection only: native Windows safeStorage has separate lifecycle evidence.
    const protection = {isEncryptionAvailable: () => true,
      encryptString(value: string) {
        const iv = randomBytes(12); const cipher = createCipheriv('aes-256-gcm', protectionKey, iv);
        return Buffer.concat([iv, cipher.update(value, 'utf8'), cipher.final(), cipher.getAuthTag()]);
      },
      decryptString(bytes: Buffer) {
        const cipher = createDecipheriv('aes-256-gcm', protectionKey, bytes.subarray(0, 12));
        cipher.setAuthTag(bytes.subarray(-16));
        return Buffer.concat([cipher.update(bytes.subarray(12, -16)), cipher.final()]).toString('utf8');
      }};
    try {
    let cookie = '';
    let loseStart = true;
    let applyCalls = 0;
    const client = createServiceClient({baseUrl: base, clearSession: async () => {cookie = '';}, fetch: async (url, init) => {
      expect(new URL(url).origin).toBe(base);
      const headers = new Headers(init.headers);
      if (cookie) headers.set('Cookie', cookie);
      const response = await fetch(url, {...init, headers});
      const session = response.headers.getSetCookie().find(value => value.startsWith('pilot_session='));
      if (session) cookie = session.split(';', 1)[0];
      expect(response.headers.get('cache-control')).toBe('no-store');
      if (init.method === 'POST' && url.endsWith('/execution-operations')) {
        applyCalls++;
        if (loseStart && response.ok) {
          loseStart = false; await response.arrayBuffer(); throw new Error('synthetic dropped receipt');
        }
      }
      return response;
    }});
    // The fixture pre-bound this key. Actual registration/PROVE is covered by the device live test.
    const identity = createDeviceIdentityController({service: client, identityFactory: () => ({prepare: async () =>
      ({state:'READY' as const, deviceId:start.device_id, credentialVersion:1})})});
    const newCoordinator = () => createExecutionSession({serviceOrigin: base, transport: identity,
      journal: createExecutionJournal({directory, protection}), vault: {read: async () => key}});
    let coordinator = newCoordinator();
    let entry = createExecutionController({identity, execution:coordinator});
    function data(result: ApiResult): any {
      expect(result.ok).toBe(true);
      if (!result.ok) throw new Error('expected successful execution HTTP response: ' + result.error);
      return result.data;
    }
    async function signed(request: ExecutionOperation) {
      const prepared = data(await client.requestExecution({operation: 'execution.prepare', payload: {request}}));
      return signExecutionOperation({key, prepared, expected: {serviceOrigin: base, userId: values.USER!, request}});
    }
    async function apply(request: ExecutionOperation) {
      const authenticated = await identity.withAuthenticatedSession(session => coordinator.submit(session, request));
      if (!authenticated.ok) throw new Error('expected current main session');
      const result = authenticated.value;
      expect(result.state).toBe('RECORDED');
      if (result.state !== 'RECORDED') throw new Error('execution must have recorded receipt');
      return {ok: true, status: 200, data: result.receipt} as const;
    }
    data(await identity.requestApi({operation: 'session.login', payload: {token: values.TOKEN}}));
    expect(await identity.prepare()).toMatchObject({state:'READY'});
    expect(await entry.execute({action:'START',requestId:start.request_id,profileVersionId:start.profile_version_id,
      strategyVersionId:start.strategy_version_id,configurationSha256:start.configuration_sha256,targets:start.targets,humanConfirmed:true}))
      .toEqual({state: 'UNKNOWN', requestId: start.request_id});
    expect(applyCalls).toBe(1);
    coordinator = newCoordinator(); // No in-memory request state retained.
    entry = createExecutionController({identity,execution:coordinator});
    const recovered = await entry.execute({action:'RECOVER',requestId:start.request_id});
    expect(recovered.state).toBe('RECORDED');
    if (recovered.state !== 'RECORDED') throw new Error('original receipt missing');
    const begun: any = recovered.receipt;
    expect(begun.status).toBe('PENDING');
    expect(applyCalls).toBe(1);
    const claim = executionOperationSchema.parse({schema_version: start.schema_version, request_id: randomUUID(),
      operation: 'CLAIM', device_id: start.device_id, credential_version: 1,
      task_id: begun.task_id, platform_run_id: begun.platform_runs[0].platform_run_id});
    const lease = data(await apply(claim));
    expect(lease).toMatchObject({status: 'RUNNING', execution_generation: 1});
    const renew = executionOperationSchema.parse({...claim, request_id: randomUUID(), operation: 'RENEW',
      lease_id: lease.lease_id, execution_generation: lease.execution_generation});
    expect(data(await apply(renew)).lease_id).toBe(lease.lease_id);
    const cancel = executionOperationSchema.parse({schema_version: start.schema_version, request_id: randomUUID(),
      operation: 'CANCEL', device_id: start.device_id, credential_version: 1, task_id: begun.task_id});
    const stale = await signed(cancel);
    const capture = await identity.withAuthenticatedSession(async session => session);
    if (!capture.ok) throw new Error('expected main session');
    data(await identity.requestApi({operation: 'session.logout'}));
    expect(await coordinator.recover(capture.value, start.request_id)).toEqual({state: 'SESSION_CHANGED'});
    expect(await client.requestExecution({operation: 'execution.receipt', payload: {request_id: start.request_id}})).toMatchObject({ok: false, status: 401});
    data(await identity.requestApi({operation: 'session.login', payload: {token: values.NEXT_TOKEN}}));
    expect(await client.requestExecution({operation: 'execution.apply', payload: stale})).toMatchObject({ok: false, error: 'invalid_proof'});
    expect(await identity.prepare()).toMatchObject({state:'READY'});
    expect(await entry.execute({action:'CANCEL',requestId:cancel.request_id,taskId:begun.task_id,humanConfirmed:true}))
      .toMatchObject({state:'RECORDED',receipt:{status: 'CANCELLING', stop_confirmed: false}});
    expect(data(await client.requestExecution({operation: 'execution.task', payload: {task_id: begun.task_id}}))).toMatchObject({status: 'CANCELLING'});
    expect(data(await client.requestExecution({operation: 'execution.receipt', payload: {request_id: start.request_id}}))).toEqual(begun);
    const list = await createExecutionController({identity,execution:newCoordinator()}).execute({action:'LIST'});
    expect(list.state).toBe('LIST');
    if (list.state === 'LIST') expect(list.requests.map(r => r.request_id).sort())
      .toEqual([start.request_id, claim.request_id, renew.request_id, cancel.request_id].sort());
    } finally {
      if (path.dirname(directory) !== path.resolve(os.tmpdir()) || !path.basename(directory).startsWith('yike-execution-live-')) throw new Error('invalid test cleanup path');
      await rm(directory, {recursive: true, force: true});
    }
  }, 30_000);
