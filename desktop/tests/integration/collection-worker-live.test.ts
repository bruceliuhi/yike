import {expect, it} from 'vitest';
import {createPrivateKey, createPublicKey, createCipheriv, createDecipheriv, randomBytes} from 'node:crypto';
import {mkdtemp, readFile, readdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createServiceClient} from '../../src/main/serviceClient';
import {createDeviceIdentityController, type DeviceWorkerScope} from '../../src/main/deviceIdentityController';
import {createCollectionWorker} from '../../src/main/collectionWorker';
import {createExecutionJournal} from '../../src/main/executionJournal';
import {createExecutionSession} from '../../src/main/executionSession';
import {createCandidateJournal} from '../../src/main/candidateJournal';
import {createCandidateSession} from '../../src/main/candidateSession';
import {executionOperationSchema} from '../../src/shared/executionOperation';
import {strategyViewSchema} from '../../src/shared/researchStrategies';
import type {ApiResult} from '../../src/shared/contracts';

const names = ['BASE', 'USER', 'TOKEN', 'SEED', 'START', 'RECORDS'] as const;
it.skipIf(!names.some(name => process.env[`YIKE_COLLECTION_WORKER_LIVE_${name}`]))(
  'composes scoped worker, real journals and HTTP, recovering one committed raw batch without another POST', async () => {
    const values = Object.fromEntries(names.map(name => [name, process.env[`YIKE_COLLECTION_WORKER_LIVE_${name}`]]));
    expect(Object.values(values).every(Boolean)).toBe(true);
    expect(Object.keys(process.env).filter(name => /DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
    expect(process.versions.node.split('.')[0]).toBe('24');
    const base = values.BASE!;
    expect(new URL(base).hostname).toBe('127.0.0.1');
    const start = executionOperationSchema.parse(JSON.parse(values.START!));
    const records: unknown[] = JSON.parse(values.RECORDS!);
    expect(records).toHaveLength(1);
    const privateKey = createPrivateKey({format: 'der', type: 'pkcs8', key: Buffer.concat([
      Buffer.from('302e020100300506032b657004220420', 'hex'), Buffer.from(values.SEED!, 'hex'),
    ])});
    const key = {scope: {serviceOrigin: base, userId: values.USER!, deviceId: start.device_id},
      privateKey: privateKey.export({format: 'pem', type: 'pkcs8'}).toString(),
      publicKey: createPublicKey(privateKey).export({format: 'jwk'}).x!};
    let cookie = '';
    let candidateWrites = 0;
    let candidatePrepares = 0;
    const candidateReads: string[] = [];
    let executionWrites = 0;
    let committedReceipt: unknown;
    const client = createServiceClient({baseUrl: base, clearSession: async () => {cookie = '';}, fetch: async (url, init) => {
      expect(new URL(url).origin).toBe(base);
      const headers = new Headers(init.headers);
      if (cookie) headers.set('Cookie', cookie);
      const response = await fetch(url, {...init, headers});
      const session = response.headers.getSetCookie().find(value => value.startsWith('pilot_session='));
      if (session) cookie = session.split(';', 1)[0];
      expect(response.headers.get('cache-control')).toBe('no-store');
      if (init.method === 'POST' && url.endsWith('/execution-operations')) executionWrites++;
      if (url.endsWith('/candidate-submission-signing-payload')) candidatePrepares++;
      if (init.method === 'GET' && new URL(url).pathname.startsWith('/api/ui/candidate-batches/')) candidateReads.push(url);
      if (init.method === 'POST' && url.endsWith('/candidate-batches')) {
        candidateWrites++;
        if (response.ok && candidateWrites === 1) {
          committedReceipt = await response.json();
          throw new Error('synthetic receipt loss after server commit');
        }
      }
      return response;
    }});
    function data(result: ApiResult): unknown {
      expect(result.ok).toBe(true);
      if (!result.ok) throw new Error('worker HTTP failed: ' + result.error);
      return result.data;
    }
    // The fixture already bound this disposable device key; not real provisioning proof.
    const identity = createDeviceIdentityController({service: client, identityFactory: () => ({prepare: async () =>
      ({state: 'READY' as const, deviceId: start.device_id, credentialVersion: start.credential_version})})});
    async function open(): Promise<DeviceWorkerScope> {
      const result = await identity.openWorkerScope();
      expect(result.ok).toBe(true);
      if (!result.ok) throw new Error('worker scope unavailable: ' + result.state);
      expect(result.scope.session.userId).toBe(values.USER);
      return result.scope;
    }
    // Test-only authenticated protection adapter, with real disk journal persistence.
    const secret = randomBytes(32);
    const protection = {isEncryptionAvailable: () => true,
      encryptString(value: string) {const nonce = randomBytes(12), cipher = createCipheriv('aes-256-gcm', secret, nonce);
        const body = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()]); return Buffer.concat([nonce, cipher.getAuthTag(), body]);},
      decryptString(value: Buffer) {const cipher = createDecipheriv('aes-256-gcm', secret, value.subarray(0, 12));
        cipher.setAuthTag(value.subarray(12, 28)); return Buffer.concat([cipher.update(value.subarray(28)), cipher.final()]).toString('utf8');}};
    const directory = await mkdtemp(path.join(tmpdir(), 'yike-worker-live-'));
    const executionDirectory = path.join(directory, 'execution');
    const candidateDirectory = path.join(directory, 'candidate');
    try {
      data(await identity.requestApi({operation: 'session.login', payload: {token: values.TOKEN}}));
      expect(await identity.prepare()).toEqual({state: 'READY', deviceId: start.device_id, credentialVersion: start.credential_version});
      const scope = await open();
      const execution = () => createExecutionSession({serviceOrigin: base, transport: scope.transport,
        journal: createExecutionJournal({directory: executionDirectory, protection}), vault: {read: async () => key}});
      const begun = await execution().submit(scope.session, start);
      expect(begun.state).toBe('RECORDED');
      if (begun.state !== 'RECORDED' || begun.receipt.operation !== 'START') throw new Error('START was not recorded');
      const strategy = strategyViewSchema.parse(data(await identity.requestApi({operation: 'strategies.get',
        payload: {strategy_version_id: start.strategy_version_id}})));
      const candidates = (active: DeviceWorkerScope) => createCandidateSession({serviceOrigin: base, transport: active.transport,
        journal: createCandidateJournal({directory: candidateDirectory, protection}), vault: {read: async () => key}});
      let driverStarts = 0, driverStops = 0;
      const worker = createCollectionWorker({execution: execution(), candidates: candidates(scope), driver: {start(input) {
        driverStarts++;
        expect(input.snapshot).toEqual(strategy.snapshot);
        expect(input.target).toEqual(start.targets![0]);
        expect(input.lease).toMatchObject({operation: 'CLAIM', task_id: begun.receipt.task_id});
        expect(input.signal.aborted).toBe(false);
        return {completed: Promise.resolve(structuredClone(records)), async stop() {driverStops++;}};
      }}});
      const result = await worker.run({scope, start, startReceipt: begun.receipt, strategy,
        platformRunId: begun.receipt.platform_runs[0].platform_run_id});
      expect(result).toMatchObject({state: 'UPLOAD_UNKNOWN', taskCompleted: false});
      if (result.state !== 'UPLOAD_UNKNOWN') throw new Error('worker must preserve lost receipt ambiguity');
      expect(scope.session.isCurrent()).toBe(false);
      expect([driverStarts, driverStops, executionWrites, candidateWrites, candidatePrepares]).toEqual([1, 1, 2, 1, 1]);
      expect(candidateReads).toEqual([]);
      const journalScope = {serviceOrigin: base, userId: values.USER!};
      const saved = await createCandidateJournal({directory: candidateDirectory, protection}).read(journalScope, result.recoveryKey);
      expect(saved?.records).toEqual(records);
      const files = await readdir(candidateDirectory); expect(files).toHaveLength(1);
      const stored = await readFile(path.join(candidateDirectory, files[0]));
      expect(stored.includes(Buffer.from((records[0] as {body: string}).body))).toBe(false);
      expect(await createExecutionJournal({directory: executionDirectory, protection}).list(journalScope))
        .toEqual(expect.arrayContaining([start, expect.objectContaining({operation: 'CLAIM'})]));
      // Fresh scope and rebuilt session/journal must recover by the original key, no new write.
      const recoveryScope = await open();
      try {
        const recovery = candidates(recoveryScope);
        expect(await recovery.list(recoveryScope.session)).toEqual({state: 'LIST', keys: [result.recoveryKey]});
        const recovered = await recovery.recover(recoveryScope.session, result.recoveryKey);
        expect(recovered).toEqual({state: 'RECORDED', receipt: committedReceipt});
        expect(recovered).toMatchObject({receipt: {accepted_count: 1, request_id: result.recoveryKey.requestId,
          platform_run_id: result.recoveryKey.platformRunId}});
        expect(candidateReads).toEqual([`${base}/api/ui/candidate-batches/${result.recoveryKey.platformRunId}/${result.recoveryKey.requestId}`]);
        expect([candidateWrites, candidatePrepares, executionWrites]).toEqual([1, 1, 2]);
      } finally {recoveryScope.close();}
    } finally {
      const cleanup = path.resolve(directory);
      if (path.dirname(cleanup) !== path.resolve(tmpdir()) || !path.basename(cleanup).startsWith('yike-worker-live-')) throw new Error('unsafe test cleanup');
      await rm(cleanup, {recursive: true, force: true});
    }
  }, 30_000);
