import type { PlatformId, TaskDraft } from "./models";
import { industryStrategyError } from './industryTaskStrategy';
import {
  confirmStrategySchema,
  prepareStrategySchema,
  revokeStrategySchema,
  strategyReceiptSchema,
  strategyViewSchema,
  type ConfirmStrategyRequest,
  type PrepareStrategyRequest,
  type RevokeStrategyRequest,
  type StrategyReceipt,
  type StrategyView,
} from "../../shared/researchStrategies";

const INVALID_DRAFT = "策略草稿配置无效，请核对后重试。";
const INVALID_RECEIPT = "策略回执无法核验，请重新查询。";
const INVALID_VIEW = "策略状态无法核验，请重新查询。";

function platformName(platform: PlatformId) {
  switch (platform) {
    case "xhs":
      return "XIAOHONGSHU" as const;
    case "douyin":
      return "DOUYIN" as const;
    case "bilibili":
      return "BILIBILI" as const;
    case "zhihu":
      return "ZHIHU" as const;
    case "web":
      return "PUBLIC_WEB" as const;
    default:
      throw new Error(INVALID_DRAFT);
  }
}

function owns(value: object, field: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(value, field);
}

export function strategyPrepareRequest(
  draft: TaskDraft,
  requestId: string,
  limits: { max_records: number; max_runtime_seconds: number },
): PrepareStrategyRequest {
  try {
    if (industryStrategyError(draft)) throw new Error(INVALID_DRAFT);
    const publicSource = draft.platforms.includes('web');
    if (publicSource && ((draft.mode !== 'once' && !(draft.mode === 'monitor' && draft.schedule.policyVersion === 1)) ||
        draft.source !== 'search' || draft.links.trim()))
      throw new Error(INVALID_DRAFT);
    if (draft.research !== undefined &&
        (owns(draft.research, "coverageProvenance") ||
          (owns(draft.research, "provenance") &&
           draft.research.provenance?.profileVersionId !== draft.profileId)))
      throw new Error(INVALID_DRAFT);
    const research = draft.research
      ? {
          version: draft.research.version,
          demandTypes: [...draft.research.demandTypes],
          maxSoubei: draft.research.maxSoubei,
          limits: {
            sources: draft.research.limits.sources,
            minutes: draft.research.limits.minutes,
            modelCalls: draft.research.limits.modelCalls,
          },
          stopAtAnyLimit: draft.research.stopAtAnyLimit,
          evidenceOrder: draft.research.evidenceOrder,
          ...(owns(draft.research, 'provenance') ? {provenance:structuredClone(draft.research.provenance)} : {}),
        }
      : null;
    return prepareStrategySchema.parse({
      schema_version: "strategy-confirmation-v1",
      request_id: requestId,
      draft_id: draft.id,
      draft_revision: draft.revision,
      profile_version_id: draft.profileId,
      configuration: {
        schema_version: "research-strategy-v1",
        name: draft.name,
        source: draft.source,
        keywords: draft.terms.map((term) => term.value),
        exclusions: draft.exclusions.map((term) => term.value),
        links: draft.links
          .split(/\r\n|\n|\r/u)
          .map((link) => link.trim())
          .filter((link) => link.length > 0),
        mode: draft.mode,
        ...(publicSource ? {publicSource:'v2ex-latest-v1' as const} : {}),
        schedule: draft.mode === 'once' ? null : {
          kind: draft.schedule.kind,
          times: [...draft.schedule.times],
          interval: draft.schedule.interval,
          start: draft.schedule.start,
          end: draft.schedule.end,
          timezone: draft.schedule.timezone,
          ...(owns(draft.schedule, "policyVersion")
            ? {
                policyVersion: (
                  draft.schedule as typeof draft.schedule & {
                    policyVersion?: unknown;
                  }
                ).policyVersion,
              }
            : {}),
        },
        research,
        ...(draft.industryStrategy ? {industryStrategy: draft.industryStrategy.configuration} : {}),
      },
      platforms: draft.platforms.map(platformName),
      max_records: limits.max_records,
      max_runtime_seconds: limits.max_runtime_seconds,
    });
  } catch {
    throw new Error(INVALID_DRAFT);
  }
}

type ParsedExpected =
  | { operation: "PREPARE"; request: PrepareStrategyRequest }
  | { operation: "CONFIRM"; request: ConfirmStrategyRequest }
  | { operation: "REVOKE"; request: RevokeStrategyRequest };

function parseExpectedRequest(value: unknown): ParsedExpected {
  const prepared = prepareStrategySchema.safeParse(value);
  if (prepared.success) return { operation: "PREPARE", request: prepared.data };
  const confirmed = confirmStrategySchema.safeParse(value);
  if (confirmed.success) return { operation: "CONFIRM", request: confirmed.data };
  const revoked = revokeStrategySchema.safeParse(value);
  if (revoked.success) return { operation: "REVOKE", request: revoked.data };
  throw new Error(INVALID_RECEIPT);
}

function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function internallyConsistent(receipt: StrategyReceipt): boolean {
  return (
    receipt.strategy_version_id === receipt.snapshot.strategy_version_id &&
    receipt.profile_version_id === receipt.snapshot.profile_version_id
  );
}

function sameImmutableBinding(
  left: StrategyReceipt | StrategyView,
  right: StrategyReceipt,
): boolean {
  return (
    left.strategy_version_id === right.strategy_version_id &&
    left.draft_id === right.draft_id &&
    left.draft_revision === right.draft_revision &&
    left.profile_version_id === right.profile_version_id &&
    left.profile_sha256 === right.profile_sha256 &&
    left.configuration_sha256 === right.configuration_sha256 &&
    sameValue(left.snapshot, right.snapshot)
  );
}

function parsePreparedBinding(value: unknown): StrategyReceipt {
  const parsed = strategyReceiptSchema.safeParse(value);
  if (
    !parsed.success ||
    parsed.data.operation !== "PREPARE" ||
    !internallyConsistent(parsed.data)
  )
    throw new Error(INVALID_RECEIPT);
  return parsed.data;
}

export function parseStrategyReceipt(
  raw: unknown,
  expectedRequest:
    | PrepareStrategyRequest
    | ConfirmStrategyRequest
    | RevokeStrategyRequest,
  preparedReceipt?: StrategyReceipt,
): StrategyReceipt {
  try {
    const expected = parseExpectedRequest(expectedRequest);
    const parsed = strategyReceiptSchema.safeParse(raw);
    if (!parsed.success || !internallyConsistent(parsed.data))
      throw new Error(INVALID_RECEIPT);
    const receipt = parsed.data;
    if (
      receipt.request_id !== expected.request.request_id ||
      receipt.operation !== expected.operation
    )
      throw new Error(INVALID_RECEIPT);

    if (expected.operation === "PREPARE") {
      const request = expected.request;
      if (
        receipt.draft_id !== request.draft_id ||
        receipt.draft_revision !== request.draft_revision ||
        receipt.profile_version_id !== request.profile_version_id ||
        receipt.snapshot.profile_version_id !== request.profile_version_id ||
        !sameValue(receipt.snapshot.configuration, request.configuration) ||
        !sameValue(receipt.snapshot.platforms, request.platforms) ||
        receipt.snapshot.max_records !== request.max_records ||
        receipt.snapshot.max_runtime_seconds !== request.max_runtime_seconds
      )
        throw new Error(INVALID_RECEIPT);
      return receipt;
    }

    const prepared = parsePreparedBinding(preparedReceipt);
    if (
      !sameImmutableBinding(receipt, prepared) ||
      receipt.strategy_version_id !== expected.request.strategy_version_id
    )
      throw new Error(INVALID_RECEIPT);
    if (expected.operation === "CONFIRM") {
      if (
        receipt.state !== "CONFIRMED" ||
        receipt.configuration_sha256 !== expected.request.configuration_sha256
      )
        throw new Error(INVALID_RECEIPT);
    } else if (receipt.state !== "REVOKED") {
      throw new Error(INVALID_RECEIPT);
    }
    return receipt;
  } catch {
    throw new Error(INVALID_RECEIPT);
  }
}

export function parseStrategyView(
  raw: unknown,
  preparedReceipt: StrategyReceipt,
): StrategyView {
  try {
    const prepared = parsePreparedBinding(preparedReceipt);
    const parsed = strategyViewSchema.safeParse(raw);
    if (
      !parsed.success ||
      parsed.data.strategy_version_id !== parsed.data.snapshot.strategy_version_id ||
      parsed.data.profile_version_id !== parsed.data.snapshot.profile_version_id ||
      !sameImmutableBinding(parsed.data, prepared)
    )
      throw new Error(INVALID_VIEW);
    return parsed.data;
  } catch {
    throw new Error(INVALID_VIEW);
  }
}
