import {describe, expect, it} from 'vitest';
import {candidateSubmissionSchema} from '../src/shared/candidateSubmission';

export function batchFixture(): any {
  return {schema_version: 'candidate-upload-v1', request_id: 'request:1', platform: 'PUBLIC_WEB', profile_version_id: 'profile-1', strategy_version_id: 'strategy-1',
    execution: {device_id: 'device-1', task_id: 'task-1', run_id: 'run-1', platform_run_id: 'platform-1', lease_id: 'lease-1', credential_version: 3, execution_generation: 1, access_mode: 'PUBLIC_ANONYMOUS', connection_id: null},
    records: [{kind: 'COMMENT', external_source_id: null, external_comment_id: 'comment-1', public_url: 'https://example.com/item', title: null, author_public_id: null, body: '  e\u0301😀\n原文\t ', published_at: null, observed_at: '2026-09-10T00:00:00Z', parent: {external_comment_id: 'parent-1'}, collector_version: 'collector-1', normalizer_version: 'normalizer-1', query: null}]};
}

describe('canonical candidate submission DTO', () => {
  it('defaults only Python optional nulls while preserving original text', () => {
    const input = batchFixture(); const result = candidateSubmissionSchema.parse(input);
    expect(result.execution.connection_version).toBeNull();
    expect(result.records[0].parent).toEqual({external_comment_id: 'parent-1', body: null, author_public_id: null, published_at: null, public_url: null});
    expect(result.records[0].body).toBe(input.records[0].body);
    expect(input.execution).not.toHaveProperty('connection_version');
  });
  it('accepts zero through 100 records and opaque IDs', () => {
    const input = batchFixture(); input.request_id = 'a' + '.:_-'.repeat(31) + 'xyz'; input.records = [];
    expect(candidateSubmissionSchema.safeParse(input).success).toBe(true);
    input.records = Array.from({length: 100}, () => batchFixture().records[0]);
    expect(candidateSubmissionSchema.safeParse(input).success).toBe(true);
    input.records.push(batchFixture().records[0]); expect(candidateSubmissionSchema.safeParse(input).success).toBe(false);
  });
  it.each(['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB'])('accepts %s account contexts', platform => {
    const input = batchFixture(); input.platform = platform; input.execution.access_mode = 'PLATFORM_ACCOUNT'; input.execution.connection_id = 'connection-1'; input.execution.connection_version = 1; input.records[0].external_source_id = 'source';
    expect(candidateSubmissionSchema.safeParse(input).success).toBe(true);
  });
  it('uses codepoint rather than UTF-16 length', () => {
    const input = batchFixture(); input.records[0].body = '😀'.repeat(20000); input.records[0].title = '😀'.repeat(512);
    expect(candidateSubmissionSchema.safeParse(input).success).toBe(true);
    input.records[0].body += 'x'; expect(candidateSubmissionSchema.safeParse(input).success).toBe(false);
  });
  it.each(['\ud800', '\udfff', 'hello\u0000', 'hello\u0085', '\t\n ', '\u00a0', ''])('rejects invalid body %j', body => {
    const input = batchFixture(); input.records[0].body = body; expect(candidateSubmissionSchema.safeParse(input).success).toBe(false);
  });
  it.each(['external_source_id', 'external_comment_id', 'title', 'author_public_id', 'published_at', 'parent', 'query'])('requires nullable record field %s', field => {
    const input = batchFixture(); delete input.records[0][field]; expect(candidateSubmissionSchema.safeParse(input).success).toBe(false);
  });
  it.each([
    (b: any) => {delete b.execution.connection_id;}, (b: any) => {b.request_id = 'a'.repeat(129);}, (b: any) => {b.request_id = '_bad';},
    (b: any) => {b.execution.credential_version = true;}, (b: any) => {b.execution.execution_generation = 0;},
    (b: any) => {b.platform = 'dy';}, (b: any) => {b.execution.connection_id = 'unexpected';},
    (b: any) => {b.execution.access_mode = 'PLATFORM_ACCOUNT';}, (b: any) => {b.platform = 'DOUYIN';},
    (b: any) => {b.records[0].kind = 'POST';}, (b: any) => {b.records[0].parent.external_comment_id = 'comment-1';},
    (b: any) => {b.records[0].observed_at = '2026-02-30T00:00:00Z';},
    (b: any) => {b.extra = 1;}, (b: any) => {b.execution.extra = 1;}, (b: any) => {b.records[0].extra = 1;}, (b: any) => {b.records[0].parent.extra = 1;},
  ])('rejects invalid shape or relations %#', mutate => {const input = batchFixture(); mutate(input); expect(candidateSubmissionSchema.safeParse(input).success).toBe(false);});
});
