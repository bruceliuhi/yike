import {expect, it} from 'vitest';
import {createPrivateKey, createPublicKey} from 'node:crypto';
import {createServiceClient} from '../../src/main/serviceClient';
import {signCandidateSubmission} from '../../src/main/candidateProofSigner';
import {candidateSubmissionSchema} from '../../src/shared/candidateSubmission';
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
    data(await client.request({operation: 'session.login', payload: {token: values.TOKEN}}));
    const prepared = data(await client.requestCandidate({operation: 'candidate.prepare', payload: {batch}}));
    const signed = signCandidateSubmission({key, prepared, expected: {serviceOrigin: base, userId: values.USER!, batch}});
    // Prepare a distinct as-yet-unsubmitted request to test session-bound proof rejection later.
    const laterBatch = {...batch, request_id: batch.request_id + '.next'};
    const laterPrepared = data(await client.requestCandidate({operation: 'candidate.prepare', payload: {batch: laterBatch}}));
    const stale = signCandidateSubmission({key, prepared: laterPrepared, expected: {serviceOrigin: base, userId: values.USER!, batch: laterBatch}});
    expect(await client.requestCandidate({operation: 'candidate.apply', payload: signed}))
      .toEqual({ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'});
    expect(writes).toBe(1);
    const original = {operation: 'candidate.receipt', payload: {platform_run_id: batch.execution.platform_run_id, request_id: batch.request_id}};
    const recovered = data(await client.requestCandidate(original));
    expect(recovered).toEqual(committedReceipt);
    expect(recovered).toMatchObject({accepted_count: 1, request_id: batch.request_id, platform_run_id: batch.execution.platform_run_id});
    expect(writes).toBe(1); expect(prepares).toBe(2);
    data(await client.request({operation: 'session.logout'}));
    expect(await client.requestCandidate(original)).toMatchObject({ok: false, status: 401});
    data(await client.request({operation: 'session.login', payload: {token: values.NEXT_TOKEN}}));
    expect(await client.requestCandidate({operation: 'candidate.apply', payload: stale})).toMatchObject({ok: false, error: 'invalid_proof'});
    expect(data(await client.requestCandidate(original))).toEqual(recovered);
    expect(writes).toBe(2); expect(prepares).toBe(2); // Historical GET needs no new signing preparation.
  }, 30_000);
