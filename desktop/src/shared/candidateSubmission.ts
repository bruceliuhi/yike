import {z} from 'zod';
import {sourceContextSchema,validAuthorTimes} from './publicAuthorContext';
import {nativeProgressBatchSchema} from './nativeSearchProgress';
const opaque = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/);
const version = z.number().int().min(1).max(2_147_483_647);
function unicode(value: string): boolean {
  return Array.from(value).every(ch => {const n = ch.codePointAt(0)!; return n < 0xd800 || n > 0xdfff;});
}
// Python str.strip whitespace, not JavaScript trim (which additionally removes BOM).
const pythonBlank = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/;
function text(maximum: number) {
  return z.string().refine(value => Array.from(value).length >= 1 && Array.from(value).length <= maximum && unicode(value) &&
    !pythonBlank.test(value) && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(value));
}
// Full URL safety/platform rules and the trusted current-time check remain server authority.
const sourceUrl = z.string().refine(value => Array.from(value).length >= 1 && Array.from(value).length <= 2048 && unicode(value));
const time = z.string().regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/).refine(value => {
  const parsed = new Date(value);
  return !value.startsWith('0000') && Number.isFinite(parsed.getTime()) && parsed.toISOString().replace('.000Z', 'Z') === value;
});
const parent = z.object({external_comment_id: text(256), body: text(20000).nullable().default(null), author_public_id: text(256).nullable().default(null),
  published_at: time.nullable().default(null), public_url: sourceUrl.nullable().default(null)}).strict();
const record = z.object({kind: z.enum(['POST', 'COMMENT', 'PAGE']), external_source_id: text(256).nullable(), external_comment_id: text(256).nullable(), public_url: sourceUrl,
  title: text(512).nullable(), author_public_id: text(256).nullable(), body: text(20000), published_at: time.nullable(), observed_at: time, parent: parent.nullable(),
  collector_version: opaque, normalizer_version: opaque, query: text(500).nullable(),source_context:sourceContextSchema.optional()}).strict().refine(value =>
  (value.kind === 'COMMENT') === (value.external_comment_id !== null) &&
  (value.parent === null || value.kind === 'COMMENT' && value.parent.external_comment_id !== value.external_comment_id) &&
  (!value.source_context || value.kind==='PAGE'&&value.external_source_id!==null&&value.author_public_id!==null&&value.normalizer_version==='v2ex-author-page-v1')&&
  validAuthorTimes(value.source_context,value.published_at,value.observed_at));
export const candidateSubmissionSchema = z.object({schema_version: z.literal('candidate-upload-v1'), request_id: opaque,
  platform: z.enum(['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB']), profile_version_id: opaque, strategy_version_id: opaque,
  execution: z.object({device_id: opaque, task_id: opaque, run_id: opaque, platform_run_id: opaque, lease_id: opaque, credential_version: version, execution_generation: version,
    access_mode: z.enum(['PLATFORM_ACCOUNT', 'PUBLIC_ANONYMOUS']), connection_id: opaque.nullable(), connection_version: version.nullable().default(null)}).strict(),
  records: z.array(record).max(100),native_progress:nativeProgressBatchSchema.optional()}).strict().refine(value => {
    const execution = value.execution;
    if(value.native_progress!==undefined&&(value.platform!=='BILIBILI'||execution.access_mode!=='PLATFORM_ACCOUNT'))return false;
    if (execution.access_mode === 'PLATFORM_ACCOUNT') {
      if (execution.connection_id === null || execution.connection_version === null) return false;
    } else if (value.platform !== 'PUBLIC_WEB' || execution.connection_id !== null || execution.connection_version !== null) return false;
    return value.records.every(item => value.platform === 'PUBLIC_WEB' || item.kind !== 'PAGE' && item.external_source_id !== null && item.source_context===undefined);
  });
export type CandidateSubmission = z.infer<typeof candidateSubmissionSchema>;
