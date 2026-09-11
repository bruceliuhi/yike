import { expect, it } from 'vitest';
import { parseRawCandidateEvidence } from '../src/shared/rawCandidateEvidence';
import { rawEvidenceFixture, rawEvidenceBinding } from './fixtures/rawCandidateEvidence';

const actionId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
function researchFixture() {
  const raw = rawEvidenceFixture(), observation = raw.observations.items[0];
  const { lease_id: _lease, execution_generation: _generation, ...context } = observation.execution_context;
  return { ...raw, candidate: { ...raw.candidate, kind: 'PAGE', external_comment_id: null,
    current_version: { ...raw.candidate.current_version, parent: null } },
    observations: { ...raw.observations, items: [{ ...observation, record_index: 0,
      content: { ...observation.content, parent: null }, request_id: actionId,
      execution_context: { ...context, kind: 'research-resource-v1', reservation_id: actionId,
        action_id: actionId, permit_id: actionId, research_generation: 1, resource: 'SOURCE_READ',
        input_sha256: 'a'.repeat(64), output_sha256: 'b'.repeat(64),
        observed_count: 3, accepted_count: 1, skipped_invalid_count: 1, skipped_budget_count: 1 } }] } };
}

it('reads research original evidence without inventing a collection lease', () => {
  const raw = researchFixture();
  expect(parseRawCandidateEvidence(raw, rawEvidenceBinding)).toEqual(raw);
  expect(raw.observations.items[0].execution_context).not.toHaveProperty('lease_id');
});

it.each([
  ['kind', 'collection'], ['action_id', 'not-uuid'], ['permit_id', ''],
  ['research_generation', 2], ['resource', 'MODEL_CALL'], ['output_sha256', 'B'.repeat(64)],
  ['input_sha256', null], ['accepted_count', 0], ['observed_count', 4],
  ['skipped_invalid_count', -1], ['skipped_budget_count', 101],
  ['lease_id', actionId], ['execution_generation', 1], ['connection_id', actionId],
  ['device_id', 'opaque-not-uuid'], ['credential_version', 0],
])('rejects invalid research context %s', (key, value) => {
  const raw = researchFixture();
  Object.assign(raw.observations.items[0].execution_context, { [key]: value });
  expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
});

it.each(['request_id', 'task_id', 'run_id', 'platform_run_id', 'platform'])('binds research observation %s', (key) => {
  const raw = researchFixture();
  Object.assign(raw.observations.items[0], { [key]: key === 'platform' ? 'DOUYIN' : 'cccccccc-cccc-4ccc-8ccc-cccccccccccc' });
  expect(() => parseRawCandidateEvidence(raw, rawEvidenceBinding)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
});
