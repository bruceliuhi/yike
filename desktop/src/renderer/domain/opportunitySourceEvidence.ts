import { z } from "zod";
import {authorUpdateBodySchema} from '../../shared/publicAuthorContext';
import {humanDemandEvidenceSchema} from '../../shared/candidateReviewApi';

const FIXED_ERROR = "INVALID_OPPORTUNITY_SOURCE_EVIDENCE";
const MAX_RESPONSE_BYTES = 2_097_152;

function hasWellFormedUnicode(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      if (index + 1 >= value.length) return false;
      const next = value.charCodeAt(index + 1);
      if (next < 0xdc00 || next > 0xdfff) return false;
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false;
    }
  }
  return true;
}

const text = z.string().min(1).refine(hasWellFormedUnicode);
const nullableText = text.nullable();
const digest = z.string().regex(/^[0-9a-f]{64}$/);
const safePositiveInteger = z.number().int().safe().positive();
const safeNonnegativeInteger = z.number().int().safe().nonnegative();

function isTimestamp(value: string): boolean {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.exec(
      value,
    );
  if (!match) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, zone] =
    match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > days[month - 1] ||
    Number(hourText) > 23 ||
    Number(minuteText) > 59 ||
    Number(secondText) > 59
  )
    return false;
  if (zone !== "Z") {
    const offsetHour = Number(zone.slice(1, 3));
    const offsetMinute = Number(zone.slice(4, 6));
    if (offsetHour > 23 || offsetMinute > 59) return false;
  }
  return true;
}

const timestamp = z.string().refine(isTimestamp);

function isSafePublicUrl(value: string): boolean {
  if (!/^https?:\/\//i.test(value) || /[\u0000-\u001f\u007f]/.test(value))
    return false;
  try {
    const parsed = new URL(value);
    return (
      (parsed.protocol === "http:" || parsed.protocol === "https:") &&
      parsed.hostname.length > 0 &&
      parsed.username.length === 0 &&
      parsed.password.length === 0
    );
  } catch {
    return false;
  }
}

const publicUrl = text.refine(isSafePublicUrl);
const parentSchema = z
  .object({
    external_comment_id: text,
    body: nullableText,
    author_public_id: nullableText,
    published_at: timestamp.nullable(),
    public_url: publicUrl.nullable(),
  })
  .strict();

const sourceSchema = z
  .object({
    platform: z.enum([
      "XIAOHONGSHU",
      "DOUYIN",
      "BILIBILI",
      "ZHIHU",
      "PUBLIC_WEB",
    ]),
    kind: z.enum(["POST", "COMMENT", "PAGE"]),
    external_source_id: nullableText,
    external_comment_id: nullableText,
    public_url: publicUrl,
    version_id: text,
    content_sha256: digest,
    title: nullableText,
    container_title: nullableText,
    body: text,
    author_public_id: nullableText,
    published_at: timestamp.nullable(),
    parent: parentSchema.nullable(),
    author_updates:z.array(authorUpdateBodySchema).max(100).refine(v=>v.reduce((n,t)=>n+Array.from(t).length,0)<=20000).optional(),
    source_read_scope:z.enum(['AUTHOR_REPLIES_COUNT_MATCHED_SUPPLEMENTS_UNREAD','AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD','HUMAN_CONFIRMED_EXCERPT']).optional(),
  })
  .strict()
  .superRefine((source, context) => {
    if((source.author_updates===undefined)!==(source.source_read_scope===undefined)||source.author_updates!==undefined&&
       (source.kind!=='PAGE'||source.platform!=='PUBLIC_WEB'||
         source.source_read_scope!=='HUMAN_CONFIRMED_EXCERPT'&&(source.author_public_id===null||source.external_source_id===null)))context.addIssue({code:'custom'});
    if (source.kind === "COMMENT") {
      if (source.external_comment_id === null || source.title !== null)
        context.addIssue({ code: "custom" });
    } else if (
      source.external_comment_id !== null ||
      source.container_title !== null ||
      source.parent !== null
    ) {
      context.addIssue({ code: "custom" });
    }
  });

const citationSchema = z
  .object({
    dimension: z.enum([
      "businessMatch",
      "intent",
      "urgency",
      "actionability",
    ]),
    field: z.union([z.enum([
      "source.title",
      "source.body",
      "source.container_title",
      "source.parent.body",
    ]),z.string().regex(/^source\.author_updates\.(?:0|[1-9][0-9]?)$/)]),
    quote: text,
  })
  .strict();

const observationSchema = z
  .object({
    id: text,
    observed_at: timestamp,
    received_at: timestamp,
  })
  .strict();

const assessmentSchema = z
  .object({
    id: text,
    assessed_at: timestamp,
    profile_version_id: text,
    profile_version: safePositiveInteger,
    strategy_version_id: text,
    provider: text,
    model: text,
    rule_version: text,
    rule_sha256: digest,
    citations: z.array(citationSchema),
    omitted_profile_citations: safeNonnegativeInteger,
  })
  .strict();

const verificationSchema = z
  .object({
    method: z.literal("HUMAN_REOPENED"),
    status_at_capture: z.literal("OPEN"),
    checked_at: timestamp,
    opening_method: z.enum(["DIRECT", "IN_PLATFORM"]),
    contact_method: z.enum(["COMMENT", "DM", "PUBLIC_CONTACT"]),
    demandEvidence: humanDemandEvidenceSchema.optional(),
    demandEvidenceId: z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/).optional(),
    checkedBy: text.refine(v => Array.from(v).length <= 256 && v.trim() === v && !/[\x00-\x1f]/.test(v)).optional(),
  })
  .strict();

function citationText(
  source: z.infer<typeof sourceSchema>,
  field: z.infer<typeof citationSchema>["field"],
): string | null {
  if(field.startsWith('source.author_updates.'))return source.author_updates?.[Number(field.split('.')[2])]??null;
  switch (field) {
    case "source.title":
      return source.title;
    case "source.body":
      return source.body;
    case "source.container_title":
      return source.container_title;
    case "source.parent.body":
      return source.parent?.body ?? null;
  }
  return null;
}

const snapshotSchema = z
  .object({
    schema_version: z.literal("opportunity-source-evidence-v1"),
    opportunity_id: text,
    captured_at: timestamp,
    source: sourceSchema,
    observation: observationSchema,
    assessment: assessmentSchema,
    verification: verificationSchema,
  })
  .strict()
  .superRefine((snapshot, context) => {
    const human = snapshot.source.source_read_scope === 'HUMAN_CONFIRMED_EXCERPT';
    const proof = snapshot.verification.demandEvidence;
    if (human !== (proof !== undefined) || human !== (snapshot.verification.demandEvidenceId !== undefined) ||
        human !== (snapshot.verification.checkedBy !== undefined)) context.addIssue({code:'custom'});
    if (proof && (snapshot.source.author_updates?.length !== 1 || snapshot.source.author_updates[0] !== proof.demandExcerpt ||
        [proof.authorExcerpt,proof.demandExcerpt,proof.dateExcerpt].some(quote =>
          ![snapshot.source.title ?? '',snapshot.source.body].some(value => value.includes(quote))))) context.addIssue({code:'custom'});
    for (const [index, citation] of snapshot.assessment.citations.entries()) {
      // The server assessment requires personal evidence for non-UNKNOWN intent.
      // This flattened snapshot omits levels and may also cite exact background.
      const addressed = citationText(snapshot.source, citation.field);
      if (addressed === null || !addressed.includes(citation.quote))
        context.addIssue({
          code: "custom",
          path: ["assessment", "citations", index],
        });
    }
  });

const evidenceSchema = z.discriminatedUnion("status", [
  z
    .object({ status: z.literal("UNAVAILABLE"), reason: z.literal("NOT_CAPTURED") })
    .strict(),
  z
    .object({
      status: z.literal("CAPTURED"),
      snapshot_sha256: digest,
      snapshot: snapshotSchema,
    })
    .strict(),
]);

export type OpportunitySourceEvidence = z.infer<typeof evidenceSchema>;

export function parseOpportunitySourceEvidence(
  raw: unknown,
  expected: { opportunityId: string; profileVersionId: string },
): OpportunitySourceEvidence {
  try {
    const serialized = JSON.stringify(raw);
    if (
      serialized === undefined ||
      new TextEncoder().encode(serialized).byteLength > MAX_RESPONSE_BYTES
    )
      throw new Error(FIXED_ERROR);
    const parsed = evidenceSchema.safeParse(raw);
    if (!parsed.success) throw new Error(FIXED_ERROR);
    if (
      parsed.data.status === "CAPTURED" &&
      (parsed.data.snapshot.opportunity_id !== expected.opportunityId ||
        parsed.data.snapshot.assessment.profile_version_id !==
          expected.profileVersionId)
    )
      throw new Error(FIXED_ERROR);
    return parsed.data;
  } catch {
    throw new Error(FIXED_ERROR);
  }
}
