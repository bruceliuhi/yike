import { z } from "zod";
import {publicSourceIdSchema} from './publicSources';
import { industryTaskStrategySchema } from './industryTaskStrategy';
import { planNativeCollectionLinks } from './nativeCollectionLinks';

const INVALID_STRATEGY_DATA = "Invalid research strategy data.";
const FORBIDDEN_UNICODE = /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const HHMM = /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/;

function exactObject<const Shape extends z.ZodRawShape>(shape: Shape) {
  const fields = new Set(Object.keys(shape));
  return z
    .record(z.string(), z.unknown(), { error: INVALID_STRATEGY_DATA })
    .superRefine((value, context) => {
      if (Object.keys(value).some((key) => !fields.has(key)))
        context.addIssue({ code: "custom", message: INVALID_STRATEGY_DATA });
    })
    .pipe(z.object(shape));
}

function distinct<T>(values: readonly T[]): boolean {
  return new Set(values).size === values.length;
}

function validUnicode(value: string): boolean {
  return !FORBIDDEN_UNICODE.test(value);
}

function owns(value: object, field: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(value, field);
}

function boundedVisibleText(maximum: number) {
  return z
    .string({ error: INVALID_STRATEGY_DATA })
    .min(1, { error: INVALID_STRATEGY_DATA })
    .refine((value) => Array.from(value).length <= maximum, {
      error: INVALID_STRATEGY_DATA,
    })
    .refine((value) => value.trim().length > 0, {
      error: INVALID_STRATEGY_DATA,
    })
    .refine(validUnicode, { error: INVALID_STRATEGY_DATA });
}

function boundedInteger(maximum: number) {
  return z
    .number({ error: INVALID_STRATEGY_DATA })
    .finite({ error: INVALID_STRATEGY_DATA })
    .int({ error: INVALID_STRATEGY_DATA })
    .min(1, { error: INVALID_STRATEGY_DATA })
    .max(maximum, { error: INVALID_STRATEGY_DATA });
}

function normalizedTerm(value: string): string {
  return value.trim().replace(/\s+/gu, " ").toLowerCase();
}

function isPrivateIpv4(hostname: string): boolean {
  const pieces = hostname.split(".");
  if (
    pieces.length !== 4 ||
    pieces.some((piece) => !/^\d{1,3}$/.test(piece) || Number(piece) > 255)
  )
    return false;
  const [first, second] = pieces.map(Number);
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168) ||
    first >= 224
  );
}

function isPlainPublicUrl(value: string): boolean {
  if (
    value.length < 1 ||
    Array.from(value).length > 2048 ||
    value.includes("\\") ||
    /\s/u.test(value) ||
    !validUnicode(value)
  )
    return false;
  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return false;
  }
  if (!validUnicode(decoded) || decoded.includes("\\")) return false;
  try {
    const url = new URL(value);
    if (
      (url.protocol !== "http:" && url.protocol !== "https:") ||
      !url.hostname ||
      url.username.length > 0 ||
      url.password.length > 0 ||
      url.port.length > 0
    )
      return false;
    const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    if (
      hostname === "localhost" ||
      hostname.endsWith(".localhost") ||
      hostname.endsWith(".local") ||
      hostname === "::" ||
      hostname === "::1" ||
      hostname.startsWith("fe80:") ||
      (hostname.includes(":") && (hostname.startsWith("fc") || hostname.startsWith("fd"))) ||
      isPrivateIpv4(hostname)
    )
      return false;
    return true;
  } catch {
    return false;
  }
}

function isAvailableTimeZone(value: string): boolean {
  if (!value || !validUnicode(value)) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: value }).format(0);
    return true;
  } catch {
    return false;
  }
}

export const strategyUuidSchema = z
  .string({ error: INVALID_STRATEGY_DATA })
  .regex(UUID, { error: INVALID_STRATEGY_DATA });
const digestSchema = z
  .string({ error: INVALID_STRATEGY_DATA })
  .regex(SHA256, { error: INVALID_STRATEGY_DATA });
const timeSchema = z
  .string({ error: INVALID_STRATEGY_DATA })
  .datetime({ offset: true, error: INVALID_STRATEGY_DATA });
const platformSchema = z.enum(
  ["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"],
  { error: INVALID_STRATEGY_DATA },
);
const platformsSchema = z
  .array(platformSchema, { error: INVALID_STRATEGY_DATA })
  .min(1, { error: INVALID_STRATEGY_DATA })
  .max(5, { error: INVALID_STRATEGY_DATA })
  .refine(distinct, { error: INVALID_STRATEGY_DATA });
const scheduleSchema = exactObject({
  kind: z.enum(["daily", "interval"], { error: INVALID_STRATEGY_DATA }),
  times: z
    .array(
      z.string({ error: INVALID_STRATEGY_DATA }).regex(HHMM, {
        error: INVALID_STRATEGY_DATA,
      }),
      { error: INVALID_STRATEGY_DATA },
    )
    .max(24, { error: INVALID_STRATEGY_DATA })
    .refine(distinct, { error: INVALID_STRATEGY_DATA }),
  interval: z
    .number({ error: INVALID_STRATEGY_DATA })
    .finite({ error: INVALID_STRATEGY_DATA })
    .min(1, { error: INVALID_STRATEGY_DATA })
    .max(168, { error: INVALID_STRATEGY_DATA }),
  start: z.string({ error: INVALID_STRATEGY_DATA }).regex(HHMM, {
    error: INVALID_STRATEGY_DATA,
  }),
  end: z.string({ error: INVALID_STRATEGY_DATA }).regex(HHMM, {
    error: INVALID_STRATEGY_DATA,
  }),
  timezone: z
    .string({ error: INVALID_STRATEGY_DATA })
    .refine(isAvailableTimeZone, { error: INVALID_STRATEGY_DATA }),
  policyVersion: z.literal(1, { error: INVALID_STRATEGY_DATA }).optional(),
})
  .superRefine((value, context) => {
    if (owns(value, "policyVersion") && value.policyVersion !== 1)
      context.addIssue({ code: "custom", message: INVALID_STRATEGY_DATA });
    if (value.policyVersion === 1 && value.kind === "interval" && value.start === value.end)
      context.addIssue({ code: "custom", message: INVALID_STRATEGY_DATA });
  })
  .refine((value) => value.kind !== "daily" || value.times.length > 0, {
    error: INVALID_STRATEGY_DATA,
  });
const researchLimitsSchema = exactObject({
  sources: boundedInteger(1_000_000),
  minutes: boundedInteger(1_000_000),
  modelCalls: boundedInteger(1_000_000),
});
const researchOriginSchema = exactObject({
  requestId: strategyUuidSchema,
  suggestionId: z.string().regex(/^suggestion_[0-9a-f]{64}$/),
  userId: boundedVisibleText(512),
  opportunityId: boundedVisibleText(512),
  profileVersionId: boundedVisibleText(512),
  sourceUrl: boundedVisibleText(2048).refine(isPlainPublicUrl),
  evidenceVersion: boundedVisibleText(512),
  accountScope: exactObject({id:boundedVisibleText(512),version:z.literal(1)}),
  // These labels retain the user's suggestion context; they are not source evidence.
  originalScope: z.string().refine(value=>Array.from(value).length<=8000&&validUnicode(value)),
  additionalScope: z.string().refine(value=>Array.from(value).length<=8000&&validUnicode(value)),
});
const researchSchema = exactObject({
  version: z.literal(1, { error: INVALID_STRATEGY_DATA }),
  demandTypes: z
    .array(
      z.enum(["INQUIRY", "COMPARISON", "REPLACEMENT", "CHANGE"], {
        error: INVALID_STRATEGY_DATA,
      }),
      { error: INVALID_STRATEGY_DATA },
    )
    .min(1, { error: INVALID_STRATEGY_DATA })
    .max(4, { error: INVALID_STRATEGY_DATA })
    .refine(distinct, { error: INVALID_STRATEGY_DATA }),
  maxSoubei: boundedInteger(1_000_000),
  limits: researchLimitsSchema,
  stopAtAnyLimit: z.literal(true, { error: INVALID_STRATEGY_DATA }),
  evidenceOrder: z.literal("SOURCE_MATCH_CONTEXT", {
    error: INVALID_STRATEGY_DATA,
  }),
  provenance: researchOriginSchema.optional(),
});
const termsSchema = z
  .array(boundedVisibleText(80), { error: INVALID_STRATEGY_DATA })
  .max(20, { error: INVALID_STRATEGY_DATA })
  .refine((values) => distinct(values.map(normalizedTerm)), {
    error: INVALID_STRATEGY_DATA,
  });
const linksSchema = z
  .array(
    z
      .string({ error: INVALID_STRATEGY_DATA })
      .refine(isPlainPublicUrl, { error: INVALID_STRATEGY_DATA }),
    { error: INVALID_STRATEGY_DATA },
  )
  .max(100, { error: INVALID_STRATEGY_DATA })
  .refine(distinct, { error: INVALID_STRATEGY_DATA });

export const platformQueriesSchema = exactObject({
  version: z.literal('platform-queries-v1'),
  items: z.array(exactObject({
    platform: z.enum(['XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU']),
    keywords: termsSchema.refine(values=>values.length>0 && values.every(value=>value===value.trim() && !value.includes(','))),
  })).min(1).max(4).refine(items=>distinct(items.map(item=>item.platform))),
});

export const strategyConfigurationSchema = exactObject({
  schema_version: z.literal("research-strategy-v1", {
    error: INVALID_STRATEGY_DATA,
  }),
  name: boundedVisibleText(60),
  source: z.enum(["search", "links"], { error: INVALID_STRATEGY_DATA }),
  keywords: termsSchema,
  exclusions: termsSchema,
  links: linksSchema,
  mode: z.enum(["once", "monitor"], { error: INVALID_STRATEGY_DATA }),
  schedule: scheduleSchema.nullable(),
  research: researchSchema.nullable(),
  industryStrategy: industryTaskStrategySchema.optional(),
  publicSource: publicSourceIdSchema.optional(),
  platformQueries: platformQueriesSchema.optional(),
})
  .superRefine((configuration, context) => {
    if(configuration.publicSource!==undefined && configuration.publicSource!==null && configuration.publicSource!=='v2ex-latest-v1' && configuration.research!==null)
      context.addIssue({code:'custom',message:INVALID_STRATEGY_DATA});
    if (configuration.platformQueries && (configuration.source!=='search' || configuration.research!==null || configuration.links.length>0 ||
        configuration.platformQueries.items.some(item=>item.keywords.some(keyword=>configuration.exclusions.some(
          exclusion=>normalizedTerm(keyword).includes(normalizedTerm(exclusion)))))))
      context.addIssue({code:'custom',message:INVALID_STRATEGY_DATA});
    if (
      (configuration.source === "search" && configuration.keywords.length === 0) ||
      (configuration.source === "links" && configuration.links.length === 0) ||
      (configuration.mode === "monitor" && configuration.schedule === null) ||
      configuration.keywords.some((keyword) =>
        configuration.exclusions.some((exclusion) =>
          normalizedTerm(keyword).includes(normalizedTerm(exclusion)),
        ),
      )
    )
      context.addIssue({ code: "custom", message: INVALID_STRATEGY_DATA });
  })
  .refine(
    (configuration) =>
      new TextEncoder().encode(JSON.stringify(configuration)).length <= 65_536,
    { error: INVALID_STRATEGY_DATA },
  );

const strategyScopeShape = {
  profile_version_id: strategyUuidSchema,
  configuration: strategyConfigurationSchema,
  platforms: platformsSchema,
  max_records: boundedInteger(10_000),
  max_runtime_seconds: boundedInteger(86_400),
} as const;
const operationShape = {
  schema_version: z.literal("strategy-confirmation-v1", {
    error: INVALID_STRATEGY_DATA,
  }),
  request_id: strategyUuidSchema,
} as const;

export const prepareStrategySchema = exactObject({
  ...operationShape,
  draft_id: strategyUuidSchema,
  draft_revision: boundedInteger(2_147_483_647),
  ...strategyScopeShape,
}).superRefine((scope, context) => {
  if (scope.configuration.platformQueries && !scope.configuration.platformQueries.items.every(
    item=>scope.platforms.includes(item.platform)))
    context.addIssue({code:'custom',message:INVALID_STRATEGY_DATA});
  if (scope.configuration.source === 'links' && scope.configuration.research === null) {
    try {
      planNativeCollectionLinks(scope.platforms, scope.configuration.links);
    } catch {
      context.addIssue({code:'custom',message:INVALID_STRATEGY_DATA});
    }
  }
});
export const confirmStrategySchema = exactObject({
  ...operationShape,
  strategy_version_id: strategyUuidSchema,
  configuration_sha256: digestSchema,
  human_confirmed: z.literal(true, { error: INVALID_STRATEGY_DATA }),
});
export const revokeStrategySchema = exactObject({
  ...operationShape,
  strategy_version_id: strategyUuidSchema,
});

const snapshotSchema = exactObject({
  profile_version_id: strategyUuidSchema,
  strategy_version_id: strategyUuidSchema,
  configuration: strategyConfigurationSchema,
  platforms: platformsSchema,
  max_records: boundedInteger(10_000),
  max_runtime_seconds: boundedInteger(86_400),
}).refine(scope=>!scope.configuration.platformQueries || scope.configuration.platformQueries.items.every(
  item=>scope.platforms.includes(item.platform)),{error:INVALID_STRATEGY_DATA});
const receiptBindingShape = {
  strategy_version_id: strategyUuidSchema,
  draft_id: strategyUuidSchema,
  draft_revision: boundedInteger(2_147_483_647),
  profile_version_id: strategyUuidSchema,
  profile_sha256: digestSchema,
  configuration_sha256: digestSchema,
  snapshot: snapshotSchema,
  state: z.enum(["DRAFT", "CONFIRMED", "REVOKED"], {
    error: INVALID_STRATEGY_DATA,
  }),
} as const;

export const strategyReceiptSchema = exactObject({
  ...operationShape,
  operation: z.enum(["PREPARE", "CONFIRM", "REVOKE"], {
    error: INVALID_STRATEGY_DATA,
  }),
  ...receiptBindingShape,
  recorded_at: timeSchema,
});
export const strategyViewSchema = exactObject({
  schema_version: z.literal("strategy-confirmation-v1", {
    error: INVALID_STRATEGY_DATA,
  }),
  ...receiptBindingShape,
  created_at: timeSchema,
  confirmed_at: timeSchema.nullable(),
  revoked_at: timeSchema.nullable(),
  is_current: z.boolean({ error: INVALID_STRATEGY_DATA }),
  profile_current: z.boolean({ error: INVALID_STRATEGY_DATA }),
});

export type StrategyConfiguration = z.infer<typeof strategyConfigurationSchema>;
/** Call only after strict configuration/scope validation. Overrides replace common terms. */
export function platformSearchKeywords(configuration: StrategyConfiguration, platform: string): string[] {
  return configuration.platformQueries?.items.find(item=>item.platform===platform)?.keywords ?? configuration.keywords;
}
export type PrepareStrategyRequest = z.infer<typeof prepareStrategySchema>;
export type ConfirmStrategyRequest = z.infer<typeof confirmStrategySchema>;
export type RevokeStrategyRequest = z.infer<typeof revokeStrategySchema>;
export type StrategyReceipt = z.infer<typeof strategyReceiptSchema>;
export type StrategyView = z.infer<typeof strategyViewSchema>;
