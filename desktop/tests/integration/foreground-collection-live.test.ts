import {expect, it, vi} from 'vitest';
import {createPrivateKey, createPublicKey, createCipheriv, createDecipheriv, randomBytes, randomUUID} from 'node:crypto';
import {mkdtemp, readFile, readdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createServiceClient} from '../../src/main/serviceClient';
import {createDeviceIdentityController} from '../../src/main/deviceIdentityController';
import {createForegroundCollectionController} from '../../src/main/foregroundCollectionController';
import {createExecutionJournal} from '../../src/main/executionJournal';
import {createExecutionSession} from '../../src/main/executionSession';
import {createCandidateJournal} from '../../src/main/candidateJournal';
import {createCandidateSession} from '../../src/main/candidateSession';
import {executionOperationSchema} from '../../src/shared/executionOperation';

const names = ['BASE', 'USER', 'TOKEN', 'SEED', 'START', 'RECORDS'] as const;
it.skipIf(!names.some(name => process.env[`YIKE_FOREGROUND_LIVE_${name}`]))(
  'real foreground controller recovers one committed upload over restricted-PG HTTP and FINISHes without recollection', async () => {
    const values = Object.fromEntries(names.map(name => [name, process.env[`YIKE_FOREGROUND_LIVE_${name}`]]));
    expect(Object.values(values).every(Boolean)).toBe(true);
    expect(Object.keys(process.env).filter(name => /DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
    expect(process.versions.node.split('.')[0]).toBe('24');
    const base = values.BASE!; expect(new URL(base).hostname).toBe('127.0.0.1');
    const start = executionOperationSchema.parse(JSON.parse(values.START!));
    const records: unknown[] = JSON.parse(values.RECORDS!); expect(records).toHaveLength(1);
    const privateKey = createPrivateKey({format: 'der', type: 'pkcs8', key: Buffer.concat([
      Buffer.from('302e020100300506032b657004220420', 'hex'), Buffer.from(values.SEED!, 'hex')])});
    const key = {scope: {serviceOrigin: base, userId: values.USER!, deviceId: start.device_id},
      privateKey: privateKey.export({format: 'pem', type: 'pkcs8'}).toString(), publicKey: createPublicKey(privateKey).export({format: 'jwk'}).x!};
    const secret = randomBytes(32);
    const protection = {isEncryptionAvailable: () => true,
      encryptString(value: string) {const nonce = randomBytes(12), cipher = createCipheriv('aes-256-gcm', secret, nonce);
        const body = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()]); return Buffer.concat([nonce, cipher.getAuthTag(), body]);},
      decryptString(value: Buffer) {const cipher = createDecipheriv('aes-256-gcm', secret, value.subarray(0, 12));
        cipher.setAuthTag(value.subarray(12, 28)); return Buffer.concat([cipher.update(value.subarray(28)), cipher.final()]).toString('utf8');}};
    const directory = await mkdtemp(path.join(tmpdir(), 'yike-foreground-live-'));
    const executionJournal = () => createExecutionJournal({directory: path.join(directory, 'execution'), protection});
    const candidateJournal = () => createCandidateJournal({directory: path.join(directory, 'candidate'), protection});
    const journalScope = {serviceOrigin: base, userId: values.USER!};
    let cookie = '', candidateWrites = 0, candidatePrepares = 0, driverStarts = 0, driverStops = 0;
    const executionWrites: string[] = [], candidateReads: string[] = [];
    let committedReceipt: any;
    const controllers: ReturnType<typeof createForegroundCollectionController>[] = [];
    const client = createServiceClient({baseUrl: base, clearSession: async () => {cookie = '';}, fetch: async (url, init) => {
      expect(new URL(url).origin).toBe(base);
      const headers = new Headers(init.headers); if (cookie) headers.set('Cookie', cookie);
      if (url.endsWith('/execution-signing-payload')) {
        const request = JSON.parse(String(init.body)).request;
        expect(await executionJournal().read(journalScope, request.request_id)).toEqual(request);
      }
      if (url.endsWith('/candidate-submission-signing-payload')) {
        const batch = JSON.parse(String(init.body)).batch; expect(driverStops).toBe(1);
        expect(await candidateJournal().read(journalScope, {platformRunId: batch.execution.platform_run_id, requestId: batch.request_id})).toEqual(batch);
        expect(batch.records).toEqual(records); candidatePrepares++;
      }
      const response = await fetch(url, {...init, headers});
      const session = response.headers.getSetCookie().find(value => value.startsWith('pilot_session='));
      if (session) cookie = session.split(';', 1)[0];
      expect(response.headers.get('cache-control')).toBe('no-store');
      if (init.method === 'POST' && url.endsWith('/execution-operations')) executionWrites.push(JSON.parse(String(init.body)).request.operation);
      if (init.method === 'GET' && new URL(url).pathname.startsWith('/api/ui/candidate-batches/')) candidateReads.push(url);
      if (init.method === 'POST' && url.endsWith('/candidate-batches')) {
        candidateWrites++;
        if (response.ok && candidateWrites === 1) {committedReceipt = await response.json(); throw new Error('controlled lost committed receipt');}
      }
      return response;
    }});
    const identity = createDeviceIdentityController({service: client, identityFactory: () => ({prepare: async () =>
      ({state: 'READY' as const, deviceId: start.device_id, credentialVersion: start.credential_version})})});
    const profileId = randomUUID();
    function controller() {
      const result = createForegroundCollectionController({serviceOrigin: base, identity,
        store: {read: async () => null}, executionJournal: executionJournal(), candidateJournal: candidateJournal(),
        configuration: {pythonExecutable: 'C:/controlled/python.exe', projectRoot: 'C:/controlled/project', runtimePath: 'C:/controlled/runtime', profileRoot: 'C:/controlled/profiles', outputRoot: 'C:/controlled/output'},
        probe: async () => true, resolveAccount: async () => ({profileId, accountPublicId: '66c01234abcdef0123456789'}),
        sessions: scope => ({execution: createExecutionSession({serviceOrigin: base, transport: scope.transport, journal: executionJournal(), vault: {read: async () => key}}),
          candidates: createCandidateSession({serviceOrigin: base, transport: scope.transport, journal: candidateJournal(), vault: {read: async () => key}})}),
        driverFactory: options => {
          expect(options.binding.expectedAccountPublicId).toBe('66c01234abcdef0123456789');
          return {start(input) {driverStarts++; expect(input.target).toEqual(start.targets![0]);
            expect(input.lease.operation).toBe('CLAIM'); expect(input.signal.aborted).toBe(false);
            return {completed: Promise.resolve(structuredClone(records)), async stop() {driverStops++;}};}};
        }});
      controllers.push(result); return result;
    }
    try {
      expect((await identity.requestApi({operation: 'session.login', payload: {token: values.TOKEN}})).ok).toBe(true);
      expect(await identity.prepare()).toEqual({state: 'READY', deviceId: start.device_id, credentialVersion: start.credential_version});
      const command = {action: 'START', humanConfirmed: true, requestId: start.request_id, profileVersionId: start.profile_version_id,
        strategyVersionId: start.strategy_version_id, configurationSha256: start.configuration_sha256, targets: start.targets};
      const first = controller(); const begun = await first.start(command);
      expect(begun.state).toBe('RECORDED');
      if (begun.state !== 'RECORDED' || begun.receipt.operation !== 'START') throw new Error('START not recorded');
      const taskId = begun.receipt.task_id;
      await vi.waitFor(async () => {expect(await first.execute({action: 'STATUS', taskId})).toMatchObject({localState: 'UPLOAD_UNKNOWN', recoverable: true});}, {timeout: 8000, interval: 50});
      expect([driverStarts, driverStops, candidateWrites, candidatePrepares]).toEqual([1, 1, 1, 1]);
      expect(executionWrites).toEqual(['START', 'CLAIM']);
      const savedKey = {platformRunId: committedReceipt.platform_run_id, requestId: committedReceipt.request_id};
      const saved = await candidateJournal().read(journalScope, savedKey); expect(saved?.records).toEqual(records);
      await first.shutdown(); const restored = controller();
      expect(await restored.start(command)).toEqual(begun); expect(driverStarts).toBe(1);
      expect(await restored.execute({action: 'RECOVER', taskId, humanConfirmed: true, retry: false})).toMatchObject({state: 'STATUS',
        localState: 'COMPLETED', serverStatus: 'SUCCEEDED', stopConfirmed: true, recordsUsed: 1, recoverable: false});
      expect(executionWrites).toEqual(['START', 'CLAIM', 'FINISH']);
      expect([driverStarts, driverStops, candidateWrites, candidatePrepares]).toEqual([1, 1, 1, 1]);
      expect(candidateReads).toEqual([`${base}/api/ui/candidate-batches/${savedKey.platformRunId}/${savedKey.requestId}`]);
      expect(await candidateJournal().read(journalScope, savedKey)).toEqual(saved);
      const files = await readdir(path.join(directory, 'candidate')); expect(files).toHaveLength(1);
      expect((await readFile(path.join(directory, 'candidate', files[0]))).includes(Buffer.from((records[0] as {body: string}).body))).toBe(false);
    } finally {
      for (const c of controllers) await c.shutdown();
      const cleanup = path.resolve(directory);
      if (path.dirname(cleanup) !== path.resolve(tmpdir()) || !path.basename(cleanup).startsWith('yike-foreground-live-')) throw new Error('unsafe fixture cleanup');
      await rm(cleanup, {recursive: true, force: true});
    }
  }, 30_000);
