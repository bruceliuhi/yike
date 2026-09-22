import { rawEvidenceFixture } from './rawCandidateEvidence';
import { capturedEvidenceFixture } from './opportunitySourceEvidence';

export function pageMetadataFixture(precision = 'DATE') {
  const value = precision === 'DATE' ? '2026-09-09' :
    precision === 'SECOND' ? '2026-09-09T01:02:03Z' : '2026-09-09T09:02:03';
  return {
    schema_version: 'public-page-metadata-v1',
    publication: {
      raw: precision === 'SECOND' ? '2026-09-09 09:02:03+08:00' : value,
      declaration: 'article:published_time', value, precision,
    } as { raw: string; declaration: string; value: string; precision: string } | null,
    author: { raw: 'TEST 编辑部', declaration: 'author', value: 'TEST 编辑部' } as
      { raw: string; declaration: string; value: string } | null,
  };
}

export function publicPageCandidateFixture(metadata = pageMetadataFixture()) {
  const raw = rawEvidenceFixture();
  const source = {
    parent: null, author_public_id: null, page_metadata: metadata,
    published_at: metadata.publication?.precision === 'SECOND' ? metadata.publication.value : null,
  };
  return {
    ...raw,
    candidate: {
      ...raw.candidate, kind: 'PAGE', external_comment_id: null,
      current_version: { ...raw.candidate.current_version, ...source },
    },
    observations: {
      ...raw.observations,
      items: raw.observations.items.map(item => ({
        ...item, normalizer_version: 'dynamic-public-read-v2',
        content: { ...item.content, ...structuredClone(source) },
      })),
    },
  };
}

export function publicPageFixedFixture(metadata = pageMetadataFixture()): any {
  const raw: any = capturedEvidenceFixture();
  Object.assign(raw.snapshot.source, {
    platform: 'PUBLIC_WEB', kind: 'PAGE', external_comment_id: null,
    title: 'TEST 网页', container_title: null, parent: null, author_public_id: null,
    page_metadata: metadata,
    published_at: metadata.publication?.precision === 'SECOND' ? metadata.publication.value : null,
  });
  raw.snapshot.assessment.citations = [{ dimension: 'intent', field: 'source.body', quote: '需要批量制作' }];
  return raw;
}
