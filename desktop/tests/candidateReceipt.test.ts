import {expect, it} from 'vitest';
import {parseCandidateReceipt} from '../src/shared/candidateReceipt';
import {recoveryBatch, recoveryReceipt, id} from './candidateRecoveryFixtures';
it('binds an immutable receipt with microsecond timestamp to the original batch', () => {
  const batch = recoveryBatch(); const raw = recoveryReceipt(batch);
  expect(parseCandidateReceipt(raw, batch)).toEqual(raw);
});
it('allows empty accepted batches and repeated candidate/version observations', () => {
  const batch = recoveryBatch(); batch.records.push({...batch.records[0]});
  expect(parseCandidateReceipt(recoveryReceipt(batch), batch).items).toHaveLength(2);
  batch.records = []; expect(parseCandidateReceipt(recoveryReceipt(batch), batch).accepted_count).toBe(0);
});
it.each(['request_id', 'task_id', 'run_id', 'platform_run_id'])('rejects mismatched %s', field => {
  const raw: any = recoveryReceipt(); raw[field] = id(99);
  expect(() => parseCandidateReceipt(raw, recoveryBatch())).toThrow(/^CANDIDATE_RECEIPT_INVALID$/);
});
it.each([{accepted_count: 0}, {accepted_count: true}, {items: []}, {extra: 1}, {schema_version: 'wrong'},
  {received_at: '2026-02-30T00:00:00Z'}, {received_at: '0000-01-01T00:00:00Z'}, {received_at: '2026-09-10'}])('rejects malformed receipt %#', change => {
  expect(() => parseCandidateReceipt({...recoveryReceipt(), ...change}, recoveryBatch())).toThrow(/^CANDIDATE_RECEIPT_INVALID$/);
});
it.each([{index: 1}, {index: false}, {candidate_id: 'bad'}, {version_id: 'bad'}, {observation_id: 'bad'}, {revision: 0}, {revision: 1.5}, {extra: 1}])('rejects malformed item %#', change => {
  const raw = recoveryReceipt(); Object.assign(raw.items[0], change);
  expect(() => parseCandidateReceipt(raw, recoveryBatch())).toThrow(/^CANDIDATE_RECEIPT_INVALID$/);
});
it('rejects duplicate observation IDs and reordered receipt items', () => {
  const batch = recoveryBatch(); batch.records.push({...batch.records[0]});
  const raw = recoveryReceipt(batch); raw.items.reverse();
  expect(() => parseCandidateReceipt(raw, batch)).toThrow();
  raw.items.reverse(); raw.items[1].observation_id = raw.items[0].observation_id;
  expect(() => parseCandidateReceipt(raw, batch)).toThrow();
});
