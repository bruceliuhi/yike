import {expect, it} from 'vitest';
import {parseCandidateReceipt} from '../src/shared/candidateReceipt';
import {recoveryBatch, recoveryReceipt, id} from './candidateRecoveryFixtures';
it('native cursor echo is exact, including on zero candidate recovery',()=>{
 const batch=recoveryBatch();batch.platform='BILIBILI';batch.execution.access_mode='PLATFORM_ACCOUNT';batch.execution.connection_id=id(5);batch.execution.connection_version=1;batch.records=[];
 const cursor={page:1,consumed_ids:[],refresh_next:false};
 batch.native_progress={schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',claim_request_id:id(99),queries:[{
  query:'设备',revision:0,base_batch_request_id:null,before:cursor,after:{...cursor,refresh_next:true},page_ids:[],processed_ids:[],has_more:false,comments_scope:'BOUNDED_SAMPLE'}]};
 const old=recoveryReceipt(batch);expect(()=>parseCandidateReceipt(old,batch)).toThrow();
 const response={...old,native_progress:structuredClone(batch.native_progress)};
 expect(parseCandidateReceipt(response,batch).native_progress).toEqual(batch.native_progress);
 response.native_progress.claim_request_id=id(98);expect(()=>parseCandidateReceipt(response,batch)).toThrow();
});
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
