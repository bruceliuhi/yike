import { z } from "zod";
import {sourceContextSchema,validAuthorTimes} from './publicAuthorContext';
import {publicPageMetadataSchema,validPageMetadataTimes} from './publicPageMetadata';
import { candidatePlatformSchema, candidateRequestIdSchema } from "./candidateReviewApi";

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
const positive = z.number().int().safe().positive();
const executionVersion = positive.max(2147483647);
const digest = z.string().regex(/^[a-f0-9]{64}$/);
const instant = z.iso.datetime({ offset: true });
// Source publication timestamps retain the upload contract's UTC-second spelling.
const published = z.iso.datetime({ precision: 0 }).nullable();
const text = (max: number) => z.string().refine((value) =>
  Array.from(value).length <= max &&
  !/^[\p{White_Space}\u001c-\u001f]*$/u.test(value) &&
  !/[\uD800-\uDFFF]/u.test(value) &&
  !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/.test(value),
);
const publicUrl = text(2048).refine((value) => {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !!url.hostname &&
      !url.username && !url.password && !/[\x00-\x20\x7f-\x9f\\]/.test(value);
  } catch { return false; }
});
const parent = z.object({
  external_comment_id: text(256),
  body: text(20000).nullable(),
  author_public_id: text(256).nullable(),
  published_at: published,
  public_url: publicUrl.nullable(),
}).strict().readonly();
const contentShape = {
  source_context:sourceContextSchema.optional(),
  page_metadata:publicPageMetadataSchema.optional(),
  public_url: publicUrl,
  // COMMENT title is the container/original-post title, never a buyer assertion.
  title: text(512).nullable(),
  author_public_id: text(256).nullable(),
  body: text(20000),
  published_at: published,
  parent: parent.nullable(),
};
const content = z.object(contentShape).strict().readonly();
type Content = z.infer<typeof content>;
const currentVersion = z.object({
  ...contentShape, version_id: uuid, content_version: digest,
}).strict().readonly();
const collectionExecutionContext = z.object({
  device_id: candidateRequestIdSchema,
  task_id: candidateRequestIdSchema,
  run_id: candidateRequestIdSchema,
  platform_run_id: candidateRequestIdSchema,
  lease_id: candidateRequestIdSchema,
  credential_version: executionVersion,
  execution_generation: executionVersion,
  access_mode: z.enum(["PLATFORM_ACCOUNT", "PUBLIC_ANONYMOUS"]),
  connection_id: candidateRequestIdSchema.nullable(),
  connection_version: executionVersion.nullable(),
}).strict().readonly();
const sampleCount = z.number().int().min(0).max(100);
const researchExecutionContext = z.object({
  kind: z.literal('research-resource-v1'),
  device_id: uuid, task_id: uuid, run_id: uuid, platform_run_id: uuid,
  credential_version: executionVersion,
  access_mode: z.literal('PUBLIC_ANONYMOUS'),
  connection_id: z.null(), connection_version: z.null(),
  reservation_id: uuid, action_id: uuid, permit_id: uuid,
  research_generation: z.literal(1), resource: z.literal('SOURCE_READ'),
  input_sha256: digest, output_sha256: digest,
  observed_count: sampleCount, accepted_count: sampleCount,
  skipped_invalid_count: sampleCount, skipped_budget_count: sampleCount,
}).strict().readonly().refine((value) => value.observed_count ===
  value.accepted_count + value.skipped_invalid_count + value.skipped_budget_count);
const executionContext = z.union([collectionExecutionContext, researchExecutionContext]);
const observation = z.object({
  observation_id: uuid,
  version_id: uuid,
  platform_run_id: uuid,
  request_id: candidateRequestIdSchema,
  record_index: z.number().int().min(0).max(99),
  observed_at: instant,
  received_at: instant,
  query: text(500).nullable(),
  collector_version: candidateRequestIdSchema,
  normalizer_version: candidateRequestIdSchema,
  task_id: uuid,
  run_id: uuid,
  execution_context: executionContext,
  platform: candidatePlatformSchema,
  profile_version_id: uuid,
  strategy_version_id: uuid,
  content_version: digest,
  content,
}).strict().readonly().refine((item) => {
  const execution = item.execution_context;
  return item.task_id === execution.task_id && item.run_id === execution.run_id &&
    item.platform_run_id === execution.platform_run_id &&
    (!('kind' in execution) || (item.request_id === execution.action_id &&
      item.record_index < execution.accepted_count)) &&
    (execution.access_mode === "PLATFORM_ACCOUNT"
      ? execution.connection_id !== null && execution.connection_version !== null
      : item.platform === "PUBLIC_WEB" && execution.connection_id === null && execution.connection_version === null);
});
const candidate = z.object({
  candidate_id: uuid,
  platform: candidatePlatformSchema,
  kind: z.enum(["POST", "COMMENT", "PAGE"]),
  external_source_id: text(256).nullable(),
  external_comment_id: text(256).nullable(),
  profile_version_id: uuid,
  strategy_version_id: uuid,
  source_identity: digest,
  revision: positive,
  ambiguous: z.boolean(),
  latest_observed_at: instant,
  current_observation_id: uuid,
  current_version: currentVersion,
  status: z.literal("UNVERIFIED"),
}).strict().readonly().refine((item) =>
  (item.kind === "COMMENT") === (item.external_comment_id !== null) &&
  (item.kind !== "PAGE" || item.platform === "PUBLIC_WEB") &&
  (item.external_source_id !== null || item.platform === "PUBLIC_WEB"),
);
const response = z.object({
  schema_version: z.literal("candidate-inbox-v1"),
  candidate,
  observations: z.object({
    items: z.array(observation).max(100).readonly(),
    total: positive,
    truncated: z.boolean(),
    // get_candidate currently has no pagination input and always selects LIMIT 100.
    page_size: z.literal(100),
  }).strict().readonly(),
}).strict().readonly();
export type RawCandidateEvidenceDto = z.infer<typeof response>;

export const expectedRawCandidateEvidenceSchema = z.object({
  candidateId: uuid,
  candidateRevision: positive,
  sourceVersionId: uuid,
  // candidate_review._capture/list maps this from raw profile_version_id, not profile_id.
  profileId: uuid,
  strategyVersionId: uuid,
  platform: candidatePlatformSchema.optional(),
}).strict();
export type ExpectedRawCandidateEvidence = z.infer<typeof expectedRawCandidateEvidenceSchema>;

function sameContent(a: Content, b: Content): boolean {
  return a.public_url === b.public_url && a.title === b.title &&
    a.author_public_id === b.author_public_id && a.body === b.body &&
    a.published_at === b.published_at &&
    // Both parents have already been parsed into the same strict ordered shape.
    JSON.stringify(a.parent) === JSON.stringify(b.parent) && JSON.stringify(a.source_context)===JSON.stringify(b.source_context) &&
    JSON.stringify(a.page_metadata) === JSON.stringify(b.page_metadata);
}

function validSourceTimes(source: Content, observedAt: string): boolean {
  const observed = Date.parse(observedAt);
  const publication = source.published_at === null ? null : Date.parse(source.published_at);
  const parentPublication = source.parent?.published_at;
  return validPageMetadataTimes(source.page_metadata,source.published_at,observedAt) &&
    validAuthorTimes(source.source_context,source.published_at,observedAt) && (publication === null || publication <= observed) &&
    (parentPublication == null || Date.parse(parentPublication) <= (publication ?? observed));
}

/** Pure read boundary: original evidence is untrusted, never an assessment or authorization. */
export function parseRawCandidateEvidence(raw: unknown, expected: unknown): RawCandidateEvidenceDto {
  try {
    const binding = expectedRawCandidateEvidenceSchema.parse(expected);
    const result = response.parse(raw), item = result.candidate, history = result.observations;
    if (item.candidate_id !== binding.candidateId || item.revision !== binding.candidateRevision ||
      item.current_version.version_id !== binding.sourceVersionId ||
      item.profile_version_id !== binding.profileId || item.strategy_version_id !== binding.strategyVersionId ||
      (binding.platform !== undefined && item.platform !== binding.platform) ||
      history.items.length !== Math.min(history.total, 100) || history.truncated !== (history.total > 100) ||
      new Set(history.items.map((entry) => entry.observation_id)).size !== history.items.length)
      throw new Error();

    const validParent = (source: Content) => (source.page_metadata === undefined ||
      item.platform === 'PUBLIC_WEB' && item.kind === 'PAGE' && source.source_context === undefined && source.author_public_id === null) &&
      (!source.source_context||item.platform==='PUBLIC_WEB'&&item.kind==='PAGE'&&
      item.external_source_id!==null&&source.author_public_id!==null) && (source.parent === null ||
      (item.kind === "COMMENT" && source.parent.external_comment_id !== item.external_comment_id));
    if (!validParent(item.current_version) ||
      !validSourceTimes(item.current_version, item.latest_observed_at)) throw new Error();
    const versions = new Map<string, { content_version: string; content: Content }>([
      [item.current_version.version_id, { content_version: item.current_version.content_version, content: item.current_version }],
    ]);
    let foundCurrent = false;
    for (const entry of history.items) {
      if (entry.platform !== item.platform || entry.profile_version_id !== item.profile_version_id ||
        entry.strategy_version_id !== item.strategy_version_id || !validParent(entry.content) ||
        !validSourceTimes(entry.content, entry.observed_at) ||
        entry.content.source_context!==undefined&&entry.normalizer_version!=='v2ex-author-page-v1' ||
        entry.content.page_metadata!==undefined&&(entry.normalizer_version!=='dynamic-public-read-v2' ||
          entry.collector_version!=='public-web-agent-v1') ||
        Date.parse(entry.observed_at) > Date.parse(entry.received_at) ||
        Date.parse(entry.observed_at) > Date.parse(item.latest_observed_at)) throw new Error();
      const known = versions.get(entry.version_id);
      if (known && (known.content_version !== entry.content_version || !sameContent(known.content, entry.content)))
        throw new Error();
      versions.set(entry.version_id, entry);
      if (entry.observation_id === item.current_observation_id) {
        foundCurrent = true;
        if (entry.version_id !== item.current_version.version_id ||
          Date.parse(entry.observed_at) !== Date.parse(item.latest_observed_at)) throw new Error();
      }
    }
    // Same-time later receipts may push the current observation beyond the 100-row window.
    if (!foundCurrent && !history.truncated) throw new Error();
    return result;
  } catch {
    throw new Error("INVALID_RAW_CANDIDATE_EVIDENCE");
  }
}
