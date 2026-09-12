import {createHash, createPublicKey, generateKeyPairSync, verify} from 'node:crypto';
import {describe, expect, it} from 'vitest';
import {signCandidateSubmission} from '../src/main/candidateProofSigner';
import {candidateSubmissionSchema} from '../src/shared/candidateSubmission';
function batchFixture(): any {
  return {schema_version: 'candidate-upload-v1', request_id: 'request:1', platform: 'PUBLIC_WEB', profile_version_id: 'profile-1', strategy_version_id: 'strategy-1',
    execution: {device_id: 'device-1', task_id: 'task-1', run_id: 'run-1', platform_run_id: 'platform-1', lease_id: 'lease-1', credential_version: 3, execution_generation: 1, access_mode: 'PUBLIC_ANONYMOUS', connection_id: null},
    records: [{kind: 'COMMENT', external_source_id: null, external_comment_id: 'comment-1', public_url: 'https://example.com/item', title: null, author_public_id: null, body: '  e\u0301😀\n原文\t ', published_at: null, observed_at: '2026-09-10T00:00:00Z', parent: {external_comment_id: 'parent-1'}, collector_version: 'collector-1', normalizer_version: 'normalizer-1', query: null}]};
}

function canonical(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
function fixture() {
  const batch = candidateSubmissionSchema.parse(batchFixture());
  const {request_id, ...hashed} = batch; const fingerprint = createHash('sha256').update(canonical(hashed)).digest('hex');
  const pair = generateKeyPairSync('ed25519');
  return {key: {scope: {serviceOrigin: 'https://pilot.example', userId: '用户😀', deviceId: batch.execution.device_id}, publicKey: pair.publicKey.export({format: 'jwk'}).x!, privateKey: pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString()},
    prepared: {signing_payload: canonical({protocol: 'yike-candidate-submission-v1', tenant_id: '租户\u2028', user_id: '用户😀', session_digest: 'b'.repeat(64), request_id, batch_fingerprint: fingerprint}), request_id, device_id: batch.execution.device_id, credential_version: batch.execution.credential_version, batch_fingerprint: fingerprint},
    expected: {serviceOrigin: 'https://pilot.example', userId: '用户😀', batch}};
}
function rejected(input: any) {expect(() => signCandidateSubmission(input)).toThrowError(/^CANDIDATE_PROOF_SIGNING_FAILED$/);}
describe('main-only candidate proof signing', () => {
  it.each([true,false])('signs boolean author read scope without dropping evidence (matched=%s)', matched => {
    const input=fixture();
    input.expected.batch.records[0]={...input.expected.batch.records[0],kind:'PAGE',external_source_id:'12',
      external_comment_id:null,author_public_id:'9',parent:null,normalizer_version:'v2ex-author-page-v1',
      source_context:{schema_version:'v2ex-author-context-v1',replies_expected:matched?1:null,replies_read:1,
        replies_complete:matched,supplements_read:false,author_replies:[{id:'29',body:'项目已结束',published_at:'2026-09-09T00:00:00Z'}]}};
    const {request_id:_,...hashed}=input.expected.batch;
    input.prepared.batch_fingerprint=createHash('sha256').update(canonical(hashed)).digest('hex');
    input.prepared.signing_payload=canonical({...JSON.parse(input.prepared.signing_payload),batch_fingerprint:input.prepared.batch_fingerprint});
    const signed=signCandidateSubmission(input);
    expect(verify(null,Buffer.from(input.prepared.signing_payload),createPublicKey(input.key.privateKey),Buffer.from(signed.signature,'base64url'))).toBe(true);
    expect(signed.batch).toEqual(input.expected.batch);
    input.expected.batch.records[0].source_context!.replies_expected=matched?null:1;
    input.expected.batch.records[0].source_context!.replies_complete=!matched;
    rejected(input);
  });
  it('signs original UTF8 bytes and returns detached normalized batch without input mutation', () => {
    const input = fixture(); const before = structuredClone(input); const signed = signCandidateSubmission(input);
    // Independent Python stdlib json.dumps(ensure_ascii=False, sort_keys=True,
    // separators=(',', ':')) over the explicitly normalized fixture (including null defaults).
    expect(input.prepared.batch_fingerprint).toBe('837efd9101b597a59146c38248dbe9b396cfd6b880200f8525ca03ffb391633b');
    expect(verify(null, Buffer.from(input.prepared.signing_payload), createPublicKey(input.key.privateKey), Buffer.from(signed.signature, 'base64url'))).toBe(true);
    expect(signed.signature).toMatch(/^[A-Za-z0-9_-]{86}$/); expect(Buffer.from(signed.signature, 'base64url').toString('base64url')).toBe(signed.signature);
    expect(input).toEqual(before); expect(signed.batch).toEqual(before.expected.batch);
    input.expected.batch.records[0].body = 'changed'; expect(signed.batch.records[0].body).toBe(before.expected.batch.records[0].body);
  });
  it('normalizes omitted null defaults before fingerprinting', () => {const input = fixture(); input.expected.batch = batchFixture(); expect(signCandidateSubmission(input).batch.execution.connection_version).toBeNull();});
  it.each(['signing_payload', 'request_id', 'device_id', 'credential_version', 'batch_fingerprint'])('requires prepared %s', field => {const input = fixture(); delete (input.prepared as any)[field]; rejected(input);});
  it.each([{request_id: 'other'}, {device_id: 'other'}, {credential_version: 4}, {credential_version: '3'}, {batch_fingerprint: 'a'.repeat(64)}, {extra: 1}])('rejects prepared mismatch %#', change => {const input = fixture(); Object.assign(input.prepared, change); rejected(input);});
  it.each([{protocol: 'yike-execution-operation-v1'}, {user_id: 'other'}, {tenant_id: ''}, {tenant_id: '\ud800'}, {request_id: 'other'}, {batch_fingerprint: 'a'.repeat(64)}, {session_digest: 'A'.repeat(64)}, {extra: 1}])('rejects signed payload mismatch %#', change => {const input = fixture(); input.prepared.signing_payload = canonical({...JSON.parse(input.prepared.signing_payload), ...change}); rejected(input);});
  it.each(['protocol', 'tenant_id', 'user_id', 'session_digest', 'request_id', 'batch_fingerprint'])('requires payload %s', field => {const input = fixture(); const p = JSON.parse(input.prepared.signing_payload); delete p[field]; input.prepared.signing_payload = canonical(p); rejected(input);});
  it.each([(s: string) => s + '\n', (s: string) => s.replace('租', '\\u79df'), (s: string) => s.replace('"protocol":', '"protocol":"bad","protocol":'), (s: string) => JSON.stringify(JSON.parse(s), null, 2)])('rejects noncanonical/duplicate bytes %#', mutate => {const input = fixture(); input.prepared.signing_payload = mutate(input.prepared.signing_payload); rejected(input);});
  it.each(['serviceOrigin', 'userId', 'deviceId'])('binds key scope %s', field => {const input = fixture(); (input.key.scope as any)[field] = 'wrong'; rejected(input);});
  it.each(['request_id', 'profile_version_id', 'strategy_version_id'])('binds batch %s', field => {const input = fixture(); (input.expected.batch as any)[field] = 'other'; rejected(input);});
  it('binds record text and order', () => {const input = fixture(); input.expected.batch.records[0].body += ' '; rejected(input); input.expected.batch.records.push({...input.expected.batch.records[0], body: 'second'}); rejected(input); input.expected.batch.records.reverse(); rejected(input);});
  it('rejects only a record order change in an otherwise valid two-record batch', () => {
    const input = fixture(); input.expected.batch.records.push({...input.expected.batch.records[0], external_comment_id: 'comment-2', body: 'second'});
    const {request_id: _requestId, ...hashed} = input.expected.batch;
    input.prepared.batch_fingerprint = createHash('sha256').update(canonical(hashed)).digest('hex');
    input.prepared.signing_payload = canonical({...JSON.parse(input.prepared.signing_payload), batch_fingerprint: input.prepared.batch_fingerprint});
    expect(signCandidateSubmission(input).batch.records).toHaveLength(2);
    input.expected.batch.records.reverse(); rejected(input);
  });
  it.each(['device_id', 'task_id', 'run_id', 'platform_run_id', 'lease_id', 'credential_version', 'execution_generation'])('binds execution field %s', field => {
    const input = fixture(); (input.expected.batch.execution as any)[field] = field.endsWith('version') || field === 'execution_generation' ? 99 : 'other'; rejected(input);
  });
  it('does not hash request_id as part of fingerprint', () => {const input = fixture(); input.prepared.batch_fingerprint = createHash('sha256').update(canonical(input.expected.batch)).digest('hex'); const p = JSON.parse(input.prepared.signing_payload); p.batch_fingerprint = input.prepared.batch_fingerprint; input.prepared.signing_payload = canonical(p); rejected(input);});
  it('rejects oversized prepared payload', () => {const input = fixture(); input.prepared.signing_payload += ' '.repeat(16384); rejected(input);});
  it('rejects mismatched keys, noncanonical PEM and non Ed25519 keys', () => {const input = fixture(); input.key.privateKey += '\n'; rejected(input); input.key.privateKey = fixture().key.privateKey; rejected(input); input.key.privateKey = generateKeyPairSync('ec', {namedCurve: 'prime256v1'}).privateKey.export({format: 'pem', type: 'pkcs8'}).toString(); rejected(input);});
  it('rejects arbitrary signing input', () => {const input = fixture(); rejected({...input, prepared: input.prepared.signing_payload});});
});
