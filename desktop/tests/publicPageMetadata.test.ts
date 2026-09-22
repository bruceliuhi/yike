import { describe, expect, it } from 'vitest';
import { parseRawCandidateEvidence } from '../src/shared/rawCandidateEvidence';
import { parseOpportunitySourceEvidence } from '../src/renderer/domain/opportunitySourceEvidence';
import { rawEvidenceBinding, rawEvidenceFixture } from './fixtures/rawCandidateEvidence';
import { capturedEvidenceFixture } from './fixtures/opportunitySourceEvidence';
import { pageMetadataFixture, publicPageCandidateFixture, publicPageFixedFixture } from './fixtures/publicPageMetadata';

const fixedBinding = { opportunityId: 'TEST-o', profileVersionId: 'TEST-p' };
const parseCandidate = (raw: unknown) => parseRawCandidateEvidence(raw, rawEvidenceBinding);
const parseFixed = (raw: unknown) => parseOpportunitySourceEvidence(raw, fixedBinding);
function rejectsMetadata(change: (metadata: any) => void) {
  const metadata = pageMetadataFixture(); change(metadata);
  expect(() => parseCandidate(publicPageCandidateFixture(metadata))).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
  expect(() => parseFixed(publicPageFixedFixture(metadata))).toThrow('INVALID_OPPORTUNITY_SOURCE_EVIDENCE');
}

describe('publisher-declared public page metadata at real evidence boundaries', () => {
  it.each(['DATE', 'LOCAL_SECOND', 'SECOND'])('preserves %s precision in candidate and fixed evidence', precision => {
    const metadata = pageMetadataFixture(precision);
    const candidate = publicPageCandidateFixture(metadata), fixed = publicPageFixedFixture(metadata);
    expect(parseCandidate(candidate)).toEqual(candidate);
    expect(parseFixed(fixed)).toEqual(fixed);
  });

  it('accepts publication-only and author-only declarations without inventing values', () => {
    for (const absent of ['publication', 'author'] as const) {
      const metadata = pageMetadataFixture(); metadata[absent] = null;
      expect(parseCandidate(publicPageCandidateFixture(metadata))).toEqual(publicPageCandidateFixture(metadata));
      expect(parseFixed(publicPageFixedFixture(metadata))).toEqual(publicPageFixedFixture(metadata));
    }
  });

  it('allows independent human-confirmed demand excerpts without promoting webpage declarations', () => {
    const raw = publicPageFixedFixture();
    raw.snapshot.source.body = 'TEST采购人于2026年9月10日表示：需要批量制作';
    Object.assign(raw.snapshot.source, {
      author_updates: ['需要批量制作'], source_read_scope: 'HUMAN_CONFIRMED_EXCERPT',
    });
    Object.assign(raw.snapshot.verification, {
      demandEvidenceId: '11111111-1111-4111-8111-111111111111', checkedBy: 'TEST reviewer',
      demandEvidence: { schemaVersion: 'human-demand-evidence-v1', authorLocator: 'TEST采购人',
        authorExcerpt: 'TEST采购人', demandExcerpt: '需要批量制作', publishedDate: '2026-09-10', dateExcerpt: '2026年9月10日' },
    });
    expect(parseFixed(raw)).toEqual(raw);
    expect(raw.snapshot.source.author_public_id).toBeNull();
    expect(raw.snapshot.source.page_metadata.publication.value).toBe('2026-09-09');
  });

  it('accepts exactly 256 Unicode author characters without treating code units as characters', () => {
    const metadata = pageMetadataFixture(); metadata.author!.raw = metadata.author!.value = '🙂'.repeat(256);
    expect(parseCandidate(publicPageCandidateFixture(metadata))).toEqual(publicPageCandidateFixture(metadata));
    expect(parseFixed(publicPageFixedFixture(metadata))).toEqual(publicPageFixedFixture(metadata));
  });

  it('preserves legacy absent fields byte-for-byte', () => {
    expect(parseCandidate(rawEvidenceFixture())).toEqual(rawEvidenceFixture());
    expect(parseFixed(capturedEvidenceFixture())).toEqual(capturedEvidenceFixture());
  });

  it.each([
    ['2024-02-29', '2024-02-29', 'DATE'],
    ['2026-09-09 09:02:03', '2026-09-09T09:02:03', 'LOCAL_SECOND'],
    ['2026-09-09T09:02:03Z', '2026-09-09T09:02:03Z', 'SECOND'],
    ['2026-09-09T09:02:03-05:30', '2026-09-09T14:32:03Z', 'SECOND'],
    ['2026-09-09T09:02:03+14:00', '2026-09-08T19:02:03Z', 'SECOND'],
  ])('normalizes only explicit ISO declaration %s', (raw, value, precision) => {
    const metadata = pageMetadataFixture();
    metadata.publication = { raw, value, precision, declaration: 'datepublished' };
    expect(parseCandidate(publicPageCandidateFixture(metadata))).toEqual(publicPageCandidateFixture(metadata));
    expect(parseFixed(publicPageFixedFixture(metadata))).toEqual(publicPageFixedFixture(metadata));
  });

  it.each([
    ['2026-02-29', '2026-02-29', 'DATE'],
    ['2026-04-31', '2026-04-31', 'DATE'],
    ['0000-01-01', '0000-01-01', 'DATE'],
    ['2026-09-09T24:00:00', '2026-09-10T00:00:00', 'LOCAL_SECOND'],
    ['2026-09-09T09:60:00', '2026-09-09T10:00:00', 'LOCAL_SECOND'],
    ['2026-09-09T09:02:60Z', '2026-09-09T09:03:00Z', 'SECOND'],
    ['2026-09-09T09:02', '2026-09-09T09:02:00', 'LOCAL_SECOND'],
    ['2026-09-09T09:02:03+14:01', '2026-09-08T19:01:03Z', 'SECOND'],
    ['2026-09-09T09:02:03+15:00', '2026-09-08T18:02:03Z', 'SECOND'],
    ['2026-09-09T09:02:03+08:60', '2026-09-09T00:02:03Z', 'SECOND'],
    ['2026-09-09T09:02:03.123Z', '2026-09-09T09:02:03Z', 'SECOND'],
    ['2026-09-09', '2026-09-09T00:00:00Z', 'SECOND'],
    ['2026-09-09T09:02:03', '2026-09-09T09:02:03Z', 'SECOND'],
    ['2026-09-09T09:02:03+08:00', '2026-09-09T09:02:03Z', 'SECOND'],
    ['2026-09-09', '2026-09-08', 'DATE'],
    ['2026-09-09\n', '2026-09-09', 'DATE'],
    ['0001-01-01T00:00:00+14:00', '0000-12-31T10:00:00Z', 'SECOND'],
    ['9999-12-31T23:59:59-14:00', '+010000-01-01T13:59:59Z', 'SECOND'],
  ])('rejects invalid calendar, precision or normalization %s -> %s', (raw, value, precision) => {
    rejectsMetadata(metadata => { metadata.publication = { raw, value, precision, declaration: 'datepublished' }; });
  });

  it.each([
    (metadata: any) => { metadata.schema_version = 'public-page-metadata-v2'; },
    (metadata: any) => { metadata.publication = null; metadata.author = null; },
    (metadata: any) => { metadata.extra = 'ignored'; },
    (metadata: any) => { delete metadata.author; },
    (metadata: any) => { metadata.publication.declaration = 'modified_time'; },
    (metadata: any) => { metadata.publication.extra = 'ignored'; },
    (metadata: any) => { metadata.publication.raw = '2'.repeat(129); },
    (metadata: any) => { metadata.author.declaration = 'og:author'; },
    (metadata: any) => { metadata.author.extra = 'ignored'; },
    (metadata: any) => { metadata.author.value = 'other identity'; },
    (metadata: any) => { metadata.author.raw = metadata.author.value = ' TEST 编辑部 '; },
    (metadata: any) => { metadata.author.raw = metadata.author.value = ''; },
    (metadata: any) => { metadata.author.raw = metadata.author.value = 'x'.repeat(257); },
    (metadata: any) => { metadata.author.raw = metadata.author.value = 'TEST\n编辑部'; },
    (metadata: any) => { metadata.author.raw = metadata.author.value = 'TEST\u007f编辑部'; },
    (metadata: any) => { metadata.author.raw = metadata.author.value = '\ud800'; },
  ])('rejects non-contract metadata or author values %#', change => rejectsMetadata(change));

  it.each(['DATE', 'LOCAL_SECOND', 'SECOND'])('rejects future %s declarations against observation, not receipt', precision => {
    rejectsMetadata(metadata => {
      const value = precision === 'DATE' ? '2026-09-11' : precision === 'LOCAL_SECOND' ?
        '2026-09-10T15:01:01' : '2026-09-10T01:01:01Z';
      metadata.publication = { raw: value, value, precision, declaration: 'datepublished' };
    });
  });

  it('accepts the possible UTC+14 wall-clock boundary without assigning a timezone', () => {
    const metadata = pageMetadataFixture('LOCAL_SECOND');
    metadata.publication!.raw = metadata.publication!.value = '2026-09-10T15:01:00';
    expect(parseCandidate(publicPageCandidateFixture(metadata))).toEqual(publicPageCandidateFixture(metadata));
    const fixed = publicPageFixedFixture(metadata);
    fixed.snapshot.observation.observed_at = '2026-09-10T01:01:00Z';
    expect(parseFixed(fixed)).toEqual(fixed);
  });

  it.each(['DATE', 'LOCAL_SECOND', 'SECOND'])('requires published_at projection to match %s precision', precision => {
    const metadata = pageMetadataFixture(precision);
    const candidate = publicPageCandidateFixture(metadata), fixed = publicPageFixedFixture(metadata);
    const wrong = precision === 'SECOND' ? null : '2026-09-09T00:00:00Z';
    candidate.candidate.current_version.published_at = candidate.observations.items[0].content.published_at = wrong;
    fixed.snapshot.source.published_at = wrong;
    expect(() => parseCandidate(candidate)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
    expect(() => parseFixed(fixed)).toThrow('INVALID_OPPORTUNITY_SOURCE_EVIDENCE');
  });

  it('rejects non-PAGE, non-PUBLIC_WEB, verified authors and author scopes', () => {
    for (const change of [
      (source: any) => { source.kind = 'POST'; },
      (source: any) => { source.platform = 'BILIBILI'; },
    ]) {
      const candidate = publicPageCandidateFixture(), fixed = publicPageFixedFixture();
      change(candidate.candidate); change(fixed.snapshot.source);
      expect(() => parseCandidate(candidate)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
      expect(() => parseFixed(fixed)).toThrow('INVALID_OPPORTUNITY_SOURCE_EVIDENCE');
    }
    const candidate: any = publicPageCandidateFixture(), fixed = publicPageFixedFixture();
    for (const source of [candidate.candidate.current_version, candidate.observations.items[0].content]) source.author_public_id = 'verified';
    fixed.snapshot.source.author_public_id = 'verified';
    expect(() => parseCandidate(candidate)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
    expect(() => parseFixed(fixed)).toThrow('INVALID_OPPORTUNITY_SOURCE_EVIDENCE');
    const context = { schema_version: 'v2ex-author-context-v1', replies_expected: 0,
      replies_read: 0, replies_complete: true, supplements_read: false, author_replies: [] };
    for (const source of [candidate.candidate.current_version, candidate.observations.items[0].content]) source.source_context = context;
    candidate.observations.items[0].normalizer_version = 'v2ex-author-page-v1';
    Object.assign(fixed.snapshot.source, { author_updates: [], source_read_scope: 'AUTHOR_REPLIES_COUNT_MATCHED_SUPPLEMENTS_UNREAD' });
    expect(() => parseCandidate(candidate)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
    expect(() => parseFixed(fixed)).toThrow('INVALID_OPPORTUNITY_SOURCE_EVIDENCE');
  });

  it('requires dynamic-public-read-v2 for metadata-bearing observations', () => {
    const raw = publicPageCandidateFixture(); raw.observations.items[0].normalizer_version = 'dynamic-public-read-v1';
    expect(() => parseCandidate(raw)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
  });

  it('checks metadata against each historical observation rather than only the latest receipt', () => {
    // Construct separately to keep current and historical content independently bound.
    const candidate = publicPageCandidateFixture();
    const previous = structuredClone(candidate.observations.items[0]);
    previous.observation_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1';
    previous.version_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
    previous.observed_at = '2026-09-07T01:01:00Z';
    candidate.observations.items.push(previous); candidate.observations.total = 2;
    expect(() => parseCandidate(candidate)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
  });

  it('binds current and repeated historical versions to identical metadata', () => {
    const current = publicPageCandidateFixture();
    current.observations.items[0].content.page_metadata.author!.raw = 'another author';
    current.observations.items[0].content.page_metadata.author!.value = 'another author';
    expect(() => parseCandidate(current)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
    const history = publicPageCandidateFixture();
    const old = structuredClone(history.observations.items[0]);
    old.observation_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1';
    old.version_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
    const replay = structuredClone(old); replay.observation_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2';
    replay.content.page_metadata.author!.raw = replay.content.page_metadata.author!.value = 'replayed author';
    history.observations.items.push(old, replay); history.observations.total = 3;
    expect(() => parseCandidate(history)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
  });
});
