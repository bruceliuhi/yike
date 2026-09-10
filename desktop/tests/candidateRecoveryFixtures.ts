import {candidateSubmissionSchema} from '../src/shared/candidateSubmission';
export const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export function recoveryBatch() {
  return candidateSubmissionSchema.parse({schema_version: 'candidate-upload-v1', request_id: 'batch:A.1',
    platform: 'PUBLIC_WEB', profile_version_id: id(1), strategy_version_id: id(2),
    execution: {device_id: id(3), task_id: id(4), run_id: id(5), platform_run_id: id(6), lease_id: id(7),
      credential_version: 1, execution_generation: 1, access_mode: 'PUBLIC_ANONYMOUS', connection_id: null},
    records: [{kind: 'PAGE', external_source_id: null, external_comment_id: null, public_url: 'https://example.com/post',
      title: null, author_public_id: null, body: '  原文 e\u0301😀\n\t ', published_at: null, observed_at: '2026-09-10T00:00:00Z',
      parent: null, collector_version: 'collector-1', normalizer_version: 'normalizer-1', query: null}]});
}
export function recoveryReceipt(batch = recoveryBatch()) {
  return {schema_version: 'candidate-receipt-v1', request_id: batch.request_id, task_id: batch.execution.task_id,
    run_id: batch.execution.run_id, platform_run_id: batch.execution.platform_run_id, accepted_count: batch.records.length,
    received_at: '2026-09-10T00:00:00.123456+00:00', items: batch.records.map((_, index) =>
      ({index, candidate_id: id(10), version_id: id(11), observation_id: id(20 + index), revision: 1}))};
}
