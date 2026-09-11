import { z } from "zod";
import type { Opportunity, PlatformId, Session } from "./models";
import { explicitInstant } from "./opportunityLibrary";
import { parseOpportunitySourceEvidence } from "./opportunitySourceEvidence";
import {researchBindingSchema} from '../../shared/opportunityResearchApi';

const id = z.string().trim().min(1).max(512);
const text = z.string().trim().min(1).max(8000);
const instant = z.string().refine(explicitInstant);
const url = z
  .string()
  .max(2048)
  .refine((value) => {
    try {
      const u = new URL(value);
      return (
        ["https:", "http:"].includes(u.protocol) && !u.username && !u.password
      );
    } catch {
      return false;
    }
  });
const platform = z.enum(["xhs", "douyin", "bilibili", "zhihu", "web"]);
const accountScopeSchema = z
  .object({
    id,
    version: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  })
  .strict();
const bindingSchema = researchBindingSchema;
export type ResearchBinding = z.infer<typeof bindingSchema>;
/** The scope must originate in the current authenticated Session, never a reply. */
export function hasResearchScope(
  scope: Session["accountScope"],
): scope is NonNullable<Session["accountScope"]> {
  return accountScopeSchema.safeParse(scope).success;
}
export function researchBinding(
  row: Opportunity,
  userId?: string,
  accountScope?: Session["accountScope"],
): ResearchBinding | null {
  if (row.sample || row.id === "sample") return null;
  const result = bindingSchema.safeParse({
    userId,
    opportunityId: row.id,
    profileVersionId: row.profileVersionId,
    sourceUrl: row.url,
    evidenceVersion: row.sourceEvidenceVersion,
    ...(accountScope ? { accountScope } : {}),
  });
  return result.success ? result.data : null;
}
export function sameResearchBinding(a: ResearchBinding, b: ResearchBinding) {
  return (
    a.userId === b.userId &&
    a.opportunityId === b.opportunityId &&
    a.profileVersionId === b.profileVersionId &&
    a.sourceUrl === b.sourceUrl &&
    a.evidenceVersion === b.evidenceVersion &&
    a.accountScope?.id === b.accountScope?.id &&
    a.accountScope?.version === b.accountScope?.version
  );
}
const quoteSchema = z
  .object({
    sourceUrl: url, evidenceVersion: id, quote: text,
    field: z.enum(['source.title', 'source.body', 'source.container_title', 'source.parent.body']).optional(),
  })
  .strict();
export type ResearchQuote = z.infer<typeof quoteSchema>;
export function researchQuoteMatches(row: Opportunity, quote: ResearchQuote): boolean {
  if (quote.sourceUrl !== row.url || quote.evidenceVersion !== row.sourceEvidenceVersion) return false;
  if (!quote.field) return row.excerpt.includes(quote.quote);
  const captured = row.sourceEvidence;
  if (captured?.status !== 'CAPTURED') return quote.field === 'source.body' && row.excerpt.includes(quote.quote);
  const source = captured.snapshot.source;
  if (source.version_id !== quote.evidenceVersion || source.public_url !== quote.sourceUrl) return false;
  const addressed = quote.field === 'source.title' ? source.title : quote.field === 'source.body' ? source.body :
    quote.field === 'source.container_title' ? source.container_title : source.parent?.body;
  return typeof addressed === 'string' && addressed.includes(quote.quote);
}
export function researchQuoteLabel(quote: ResearchQuote): string {
  return quote.field === 'source.title' ? '原帖标题' : quote.field === 'source.container_title' ? '所属帖子标题' :
    quote.field === 'source.parent.body' ? '上级评论（上下文）' : '来源正文';
}
export const RESEARCH_CATEGORIES = {
  OPPORTUNITY: "明确需求",
  OBSERVATION: "观察池",
  EXCLUDED: "已排除",
  UNASSESSED: "待分类",
} as const;
export type ResearchCategory = keyof typeof RESEARCH_CATEGORIES;
const classificationSchema = z
  .object({
    category: z.enum(["OPPORTUNITY", "OBSERVATION", "EXCLUDED", "UNASSESSED"]),
    type: z.string().max(80),
    reason: text,
    ruleVersion: id,
    evidence: z.array(quoteSchema).max(30),
    review: z
      .object({
        status: z.enum(["PENDING", "RECOGNIZED", "NEEDS_EVIDENCE"]),
        reviewer: z.string().max(512),
        reviewedAt: instant.nullable(),
      })
      .strict(),
  })
  .strict();
export type ResearchClassification = z.infer<typeof classificationSchema>;
const opportunitySchema = z
  .object({
    id,
    title: text,
    buyer: z.string().max(2000),
    summary: z.string().max(8000),
    excerpt: z.string().max(40000),
    matchReason: z.string().max(8000),
    actionSignal: z.string().max(8000),
    value: z.string().max(8000),
    risk: z.string().max(8000),
    contactPath: z.string().max(8000),
    url,
    platform: z.string().min(1).max(128),
    sourceStatus: id,
    profileStatus: id,
    profileVersionId: id,
    reviewer: z.string().max(512),
    reviewedAt: z.string().max(80),
    publishedAt: z.string().max(80),
    updatedAt: z.string().max(80),
    intentStatus: id,
    comment: z.string().max(40000),
    dm: z.string().max(40000),
    sourceEvidenceVersion: id.optional(),
    sourceObservedAt: z.string().optional(),
    sample: z.literal(false).optional(),
    libraryFacts: z.unknown().optional(),
    sourceEvidence: z.unknown().optional(),
  })
  .passthrough();
const recordSchema = z
  .object({
    opportunity: opportunitySchema,
    classification: classificationSchema,
  })
  .strict();
export interface ResearchRecord {
  opportunity: Opportunity;
  classification: ResearchClassification;
}
const listSchema = z
  .object({
    schemaVersion: z.literal(1),
    userId: id,
    accountScope: accountScopeSchema,
    snapshotId: id,
    generatedAt: instant,
    expiresAt: instant,
    records: z.array(recordSchema).max(1000),
  })
  .strict();
export interface ResearchCollection {
  schemaVersion: 1;
  userId: string;
  accountScope: NonNullable<Session["accountScope"]>;
  snapshotId: string;
  generatedAt: string;
  expiresAt: string;
  records: ResearchRecord[];
}
function invalid(
  message = "研究数据的身份或证据版本不匹配，请刷新重试。",
): never {
  throw new Error(message);
}
function fresh(generatedAt: string, expiresAt: string, now: number) {
  const generated = Date.parse(generatedAt),
    expires = Date.parse(expiresAt);
  if (generated >= expires || generated > now + 5 * 60_000)
    invalid("研究快照时间不一致，请刷新后继续。");
  if (expires <= now) invalid("研究快照已过期，请刷新后继续。");
}
export function parseResearchCollection(
  raw: unknown,
  userId: string,
  now = Date.now(),
  accountScope?: Session["accountScope"],
): ResearchCollection {
  const result = listSchema.safeParse(raw);
  if (
    !hasResearchScope(accountScope) ||
    !result.success ||
    result.data.userId !== userId ||
    result.data.accountScope?.id !== accountScope?.id ||
    result.data.accountScope?.version !== accountScope?.version
  )
    invalid();
  const data = result.data;
  fresh(data.generatedAt, data.expiresAt, now);
  const seen = new Set<string>(),
    sources = new Set<string>();
  for (const record of data.records) {
    const row = record.opportunity,
      c = record.classification;
    if (Object.hasOwn(row, "sourceEvidence")) {
      try {
        row.sourceEvidence = parseOpportunitySourceEvidence(row.sourceEvidence, {
          opportunityId: row.id,
          profileVersionId: row.profileVersionId,
        });
      } catch {
        invalid("原文证据响应不完整，请重新读取。");
      }
    }
    // Different comments often share the post URL. Only a captured source
    // identity or immutable version identifies evidence; legacy IDs do not.
    const captured=row.sourceEvidence as Opportunity['sourceEvidence'];
    const source=captured?.status==='CAPTURED'?captured.snapshot.source:null;
    const sourceKey = JSON.stringify([row.profileVersionId, source
      ? [source.platform,source.kind,source.external_source_id,source.external_comment_id,source.public_url]
      : [row.url,row.sourceEvidenceVersion ?? row.id]]);
    if (row.id === "sample" || seen.has(row.id) || sources.has(sourceKey))
      invalid();
    seen.add(row.id);
    sources.add(sourceKey);
    if(!row.sourceEvidenceVersion && (c.category!=='UNASSESSED'||c.evidence.length||c.review.status==='RECOGNIZED'))invalid();
    if (c.category !== "UNASSESSED" && !c.evidence.length) invalid();
    if (
      c.review.status === "RECOGNIZED" &&
      (!c.review.reviewer.trim() || !c.review.reviewedAt)
    )
      invalid();
    for (const q of c.evidence)
      if (
        q.sourceUrl !== row.url ||
        q.evidenceVersion !== row.sourceEvidenceVersion ||
        !researchQuoteMatches(row as Opportunity, q)
      )
        invalid();
  }
  return data as ResearchCollection;
}
const sourceVersionSchema = z
  .object({
    id,
    ordinal: z.number().int().positive(),
    previousVersionId: id.nullable(),
    sourceUrl: url,
    content: z.string().min(1).max(40000).refine(value=>value.trim().length>0),
    publishedAt: instant.nullable(),
    observedAt: instant.nullable(),
    access: z.enum(["AVAILABLE", "FAILED", "UNKNOWN"]),
  })
  .strict();
const changeSchema = z
  .object({
    id,
    kind: z.enum(["CONTENT", "BUDGET", "DEADLINE", "CLOSED"]),
    label: text,
    from: quoteSchema,
    to: quoteSchema,
    occurredAt: instant.nullable(),
  })
  .strict();
const contactSchema = z
  .object({
    id,
    opportunityId: id,
    kind: z.enum(["MANUAL", "CHANNEL"]),
    label: text,
    detail: text,
    occurredAt: instant.nullable(),
    recordedAt: instant,
    operator: z.string().max(512),
    receiptId: z.string().max(512),
  })
  .strict();
const timelineSchema = z
  .object({
    schemaVersion: z.literal(1),
    binding: bindingSchema,
    snapshotId: id,
    generatedAt: instant,
    expiresAt: instant,
    versions: z.array(sourceVersionSchema).min(1).max(100),
    changes: z.array(changeSchema).max(200),
    contacts: z.array(contactSchema).max(200),
    gaps: z.array(text).max(30),
  })
  .strict();
const timelineV2Schema = timelineSchema.extend({
  schemaVersion: z.literal(2),
  anchorObservationId: id,
  observations: z.array(z.object({id,versionId:id,observedAt:instant,receivedAt:instant}).strict()).min(1).max(200),
  changes: z.array(changeSchema.extend({
    kind:z.literal('CONTENT'),occurredAt:z.null(),fromObservationId:id,toObservationId:id,detectedAt:instant,
  })).max(200),
});
const timelineWireSchema=z.discriminatedUnion('schemaVersion',[timelineSchema,timelineV2Schema]);
export type ResearchTimeline = z.infer<typeof timelineWireSchema>;
function validateObservationChanges(data:z.infer<typeof timelineV2Schema>){
  const versions=new Map(data.versions.map(v=>[v.id,v]));
  const observations=new Map<string,typeof data.observations[number]>();
  const groups:{at:number;ids:Set<string>;bodies:Set<string>}[]=[];
  const firstVersions:string[]=[];
  for(const observation of data.observations){
    const at=Date.parse(observation.observedAt),received=Date.parse(observation.receivedAt);
    const version=versions.get(observation.versionId);
    if(!version||observations.has(observation.id)||at>Date.parse(data.generatedAt)||received>Date.parse(data.generatedAt)||
      (groups.length&&at<groups.at(-1)!.at))invalid();
    observations.set(observation.id,observation);
    if(!firstVersions.includes(observation.versionId))firstVersions.push(observation.versionId);
    if(!groups.length||groups.at(-1)!.at!==at)groups.push({at,ids:new Set(),bodies:new Set()});
    groups.at(-1)!.ids.add(observation.id);groups.at(-1)!.bodies.add(version.content);
  }
  if(firstVersions.length!==versions.size||data.versions.some((v,i)=>v.id!==firstVersions[i]||v.ordinal!==i+1))invalid();
  const anchor=observations.get(data.anchorObservationId);
  if(!anchor||anchor.versionId!==data.binding.evidenceVersion)invalid();
  const anchorAt=Date.parse(anchor.observedAt),expected=new Set<number>();
  for(let i=1;i<groups.length;i++){
    const before=groups[i-1],after=groups[i];
    if(before.at>=anchorAt&&after.at>anchorAt&&before.bodies.size===1&&after.bodies.size===1&&
      [...before.bodies][0]!==[...after.bodies][0])expected.add(i);
  }
  for(const change of data.changes){
    const from=observations.get(change.fromObservationId),to=observations.get(change.toObservationId);
    const group=groups.findIndex(item=>item.ids.has(change.toObservationId));
    if(!from||!to||!expected.has(group)||!groups[group-1]?.ids.has(change.fromObservationId)||
      from.versionId!==change.from.evidenceVersion||to.versionId!==change.to.evidenceVersion||
      Date.parse(change.detectedAt)!==Math.max(Date.parse(from.receivedAt),Date.parse(to.receivedAt))||
      [change.from,change.to].some(q=>q.field!==undefined&&q.field!=='source.body'))invalid();
    expected.delete(group);
  }
  if(expected.size)invalid();
}
export function parseResearchTimeline(
  raw: unknown,
  binding: ResearchBinding,
  now = Date.now(),
): ResearchTimeline {
  const result = timelineWireSchema.safeParse(raw);
  if (!result.success || !sameResearchBinding(result.data.binding, binding))
    invalid();
  const data = result.data;
  fresh(data.generatedAt, data.expiresAt, now);
  const versions = new Map<string, ResearchTimeline["versions"][number]>();
  data.versions.forEach((v, index) => {
    if (
      v.sourceUrl !== binding.sourceUrl ||
      versions.has(v.id) ||
      (index === 0
        ? v.previousVersionId !== null
        : v.previousVersionId !== data.versions[index - 1].id ||
          v.ordinal <= data.versions[index - 1].ordinal)
    )
      invalid();
    versions.set(v.id, v);
  });
  if(data.schemaVersion===2)validateObservationChanges(data);
  else if (data.versions.at(-1)?.id !== binding.evidenceVersion) invalid();
  const ids = new Set<string>();
  for (const change of data.changes) {
    if (ids.has(change.id)) invalid();
    ids.add(change.id);
    const before = versions.get(change.from.evidenceVersion),
      after = versions.get(change.to.evidenceVersion);
    if (!before || !after || (data.schemaVersion===1&&before.ordinal >= after.ordinal)) invalid();
    for (const q of [change.from, change.to])
      if (
        q.sourceUrl !== binding.sourceUrl ||
        !versions.get(q.evidenceVersion)?.content.includes(q.quote)
      )
        invalid();
  }
  for (const contact of data.contacts) {
    if (
      ids.has(contact.id) ||
      contact.opportunityId !== binding.opportunityId ||
      (contact.kind === "CHANNEL"
        ? !contact.receiptId.trim()
        : !contact.operator.trim())
    )
      invalid();
    ids.add(contact.id);
  }
  return data;
}
const usageSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("UNKNOWN"), reason: text }).strict(),
  z
    .object({
      status: z.enum(["ESTIMATED", "METERED"]),
      amount: z.number().finite().nonnegative(),
      unit: z.literal("搜贝"),
      basis: text,
      measuredAt: instant,
    })
    .strict(),
]);
export type ResearchUsage = z.infer<typeof usageSchema>;
const similarSchema = z
  .object({
    schemaVersion: z.literal(1),
    requestId: id,
    suggestionId: id,
    binding: bindingSchema,
    generatedAt: instant,
    expiresAt: instant,
    eligible: z.boolean(),
    ineligibleReason: z.string().max(2000),
    recognition: z
      .object({ reviewer: id, reviewedAt: instant, evidenceVersion: id })
      .strict()
      .nullable(),
    rationale: text,
    evidence: z.array(quoteSchema).min(1).max(20),
    profileId: id,
    profileVersion: z.number().int().positive(),
    keywords: z.array(z.string().trim().min(1).max(120)).min(1).max(20),
    exclusions: z.array(z.string().trim().min(1).max(120)).max(20),
    supportedPlatforms: z.array(platform).min(1).max(5),
    originalScope: text,
    additionalScope: text,
    usage: usageSchema,
  })
  .strict();
export type SimilarResearchPlan = z.infer<typeof similarSchema>;
export function parseSimilarResearch(
  raw: unknown,
  binding: ResearchBinding,
  requestId: string,
  now = Date.now(),
): SimilarResearchPlan {
  const result = similarSchema.safeParse(raw);
  if (
    !result.success ||
    !sameResearchBinding(result.data.binding, binding) ||
    result.data.requestId !== requestId
  )
    invalid();
  const data = result.data;
  fresh(data.generatedAt, data.expiresAt, now);
  if (
    data.eligible &&
    (!data.recognition ||
      data.recognition.evidenceVersion !== binding.evidenceVersion)
  )
    invalid();
  if (new Set(data.supportedPlatforms).size !== data.supportedPlatforms.length)
    invalid();
  for (const q of data.evidence)
    if (
      q.sourceUrl !== binding.sourceUrl ||
      q.evidenceVersion !== binding.evidenceVersion
    )
      invalid();
  return data;
}
/** A local, idempotent draft handoff; never starts a run or contacts a customer. */
export interface SimilarResearchHandoff {
  requestId: string;
  draftId: string;
  binding: ResearchBinding;
  suggestionId: string;
  name: string;
  profileId: string;
  profileVersion: number;
  keywords: string[];
  exclusions: string[];
  platforms: PlatformId[];
  originalScope: string;
  additionalScope: string;
  limits: {
    sources: number;
    minutes: number;
    soubei: number | null;
    stopAtAnyLimit: true;
  };
  usage: ResearchUsage;
}
export type SimilarDraftHandoff = (input: SimilarResearchHandoff) => void;
