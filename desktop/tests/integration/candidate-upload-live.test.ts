import {expect, it} from 'vitest';
import {createPrivateKey, createPublicKey, createCipheriv, createDecipheriv, randomBytes} from 'node:crypto';
import {mkdtemp, readFile, readdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createServiceClient} from '../../src/main/serviceClient';
import {signCandidateSubmission} from '../../src/main/candidateProofSigner';
import {candidateSubmissionSchema} from '../../src/shared/candidateSubmission';
import {createCandidateJournal} from '../../src/main/candidateJournal';
import {createCandidateSession} from '../../src/main/candidateSession';
import type {ApiResult} from '../../src/shared/contracts';

const names = ['BASE', 'USER', 'TOKEN', 'NEXT_TOKEN', 'SEED', 'BATCH'] as const;
it.skipIf(!names.some(name => process.env[`YIKE_CANDIDATE_UPLOAD_LIVE_${name}`]))(
  'uploads original evidence over HTTP and recovers a lost receipt without repeating the write', async () => {
    const values = Object.fromEntries(names.map(name => [name, process.env[`YIKE_CANDIDATE_UPLOAD_LIVE_${name}`]]));
    expect(Object.values(values).every(Boolean)).toBe(true);
    expect(Object.keys(process.env).filter(name => /DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
    expect(process.versions.node.split('.')[0]).toBe('24');
    const base = values.BASE!;
    expect(new URL(base).hostname).toBe('127.0.0.1');
    const batch = candidateSubmissionSchema.parse(JSON.parse(values.BATCH!));
    const privateKey = createPrivateKey({format: 'der', type: 'pkcs8', key: Buffer.concat([
      Buffer.from('302e020100300506032b657004220420', 'hex'), Buffer.from(values.SEED!, 'hex'),
    ])});
    const key = {scope: {serviceOrigin: base, userId: values.USER!, deviceId: batch.execution.device_id},
      privateKey: privateKey.export({format: 'pem', type: 'pkcs8'}).toString(),
      publicKey: createPublicKey(privateKey).export({format: 'jwk'}).x!};
    let cookie = '';
    let loseReceipt = true;
    let writes = 0;
    let prepares = 0;
    let committedReceipt: unknown;
    const client = createServiceClient({baseUrl: base, clearSession: async () => {cookie = '';}, fetch: async (url, init) => {
      expect(new URL(url).origin).toBe(base);
      const headers = new Headers(init.headers);
      if (cookie) headers.set('Cookie', cookie);
      const response = await fetch(url, {...init, headers});
      const session = response.headers.getSetCookie().find(value => value.startsWith('pilot_session='));
      if (session) cookie = session.split(';', 1)[0];
      expect(response.headers.get('cache-control')).toBe('no-store');
      if (url.endsWith('/candidate-submission-signing-payload')) prepares++;
      if (init.method === 'POST' && url.endsWith('/candidate-batches')) {
        writes++;
        if (loseReceipt && response.ok) {
          committedReceipt = await response.json(); loseReceipt = false;
          throw new Error('synthetic receipt loss after commit');
        }
      }
      return response;
    }});
    function data(result: ApiResult): any {
      expect(result.ok).toBe(true);
      if (!result.ok) throw new Error('HTTP candidate failure: ' + result.error);
      return result.data;
    }
    // Test-only authenticated protection adapter; real disk, not Electron safeStorage evidence.
    const secret = randomBytes(32);
    const protection = {isEncryptionAvailable: () => true,
      encryptString(value: string) {const nonce = randomBytes(12), cipher = createCipheriv('aes-256-gcm', secret, nonce);
        const body = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()]); return Buffer.concat([nonce, cipher.getAuthTag(), body]);},
      decryptString(value: Buffer) {const cipher = createDecipheriv('aes-256-gcm', secret, value.subarray(0, 12));
        cipher.setAuthTag(value.subarray(12, 28)); return Buffer.concat([cipher.update(value.subarray(28)), cipher.final()]).toString('utf8');}};
    const directory = await mkdtemp(path.join(tmpdir(), 'yike-candidate-recovery-'));
    try {
    const session = {userId: values.USER!, sessionId: '00000000-0000-4000-8000-000000000001', isCurrent: () => true};
    const originalKey = {platformRunId: batch.execution.platform_run_id, requestId: batch.request_id};
    const coordinator = () => createCandidateSession({serviceOrigin: base, journal: createCandidateJournal({directory, protection}),
      vault: {read: async () => key}, transport: client});
    data(await client.request({operation: 'session.login', payload: {token: values.TOKEN}}));
    // Prepare a distinct as-yet-unsubmitted request to test session-bound proof rejection later.
    const laterBatch = {...batch, request_id: batch.request_id + '.next'};
    const laterPrepared = data(await client.requestCandidate({operation: 'candidate.prepare', payload: {batch: laterBatch}}));
    const stale = signCandidateSubmission({key, prepared: laterPrepared, expected: {serviceOrigin: base, userId: values.USER!, batch: laterBatch}});
    expect(await coordinator().submit(session, batch)).toEqual({state: 'UNKNOWN', key: originalKey});
    expect(writes).toBe(1);
    const original = {operation: 'candidate.receipt', payload: {platform_run_id: batch.execution.platform_run_id, request_id: batch.request_id}};
    const files = await readdir(directory); expect(files).toHaveLength(1);
    const stored = await readFile(path.join(directory, files[0]));
    expect(stored.includes(Buffer.from(batch.records[0].body))).toBe(false);
    expect(JSON.parse(protection.decryptString(stored)).batch).toEqual(batch);
    // Recreate both journal and session: recovery cannot depend on in-memory batch state.
    const recovery = coordinator();
    expect(await recovery.list(session)).toEqual({state: 'LIST', keys: [originalKey]});
    const result = await recovery.recover(session, originalKey);
    expect(result.state).toBe('RECORDED');
    if (result.state !== 'RECORDED') throw new Error('candidate recovery failed');
    const recovered = result.receipt;
    expect(recovered).toEqual(committedReceipt);
    expect(recovered).toMatchObject({accepted_count: 1, request_id: batch.request_id, platform_run_id: batch.execution.platform_run_id});
    expect(writes).toBe(1); expect(prepares).toBe(2);
    data(await client.request({operation: 'session.logout'}));
    expect(await client.requestCandidate(original)).toMatchObject({ok: false, status: 401});
    data(await client.request({operation: 'session.login', payload: {token: values.NEXT_TOKEN}}));
    expect(await client.requestCandidate({operation: 'candidate.apply', payload: stale})).toMatchObject({ok: false, error: 'invalid_proof'});
    expect(await coordinator().recover({...session, sessionId: '00000000-0000-4000-8000-000000000002'}, originalKey))
      .toEqual({state: 'RECORDED', receipt: recovered});
    expect(writes).toBe(2); expect(prepares).toBe(2); // Historical GET needs no new signing preparation.
    } finally {await rm(directory, {recursive: true, force: true});}
  }, 30_000);
