import { z } from "zod";
import type { Opportunity } from "./models";

// A date without a zone or a rolled-over calendar date is not a deadline.
export function explicitInstant(value: string): boolean {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,3})?(Z|[+-]\d{2}:\d{2})$/.exec(
      value,
    );
  if (!match) return false;
  const [, year, month, day, hour, minute, second, zone] = match;
  const y = Number(year),
    m = Number(month),
    d = Number(day);
  if (
    y < 1000 ||
    m < 1 ||
    m > 12 ||
    d < 1 ||
    d > new Date(Date.UTC(y, m, 0)).getUTCDate() ||
    Number(hour) > 23 ||
    Number(minute) > 59 ||
    Number(second) > 59
  )
    return false;
  if (zone !== "Z") {
    const h = Number(zone.slice(1, 3)),
      minutes = Number(zone.slice(4));
    if (
      zone === "-00:00" ||
      h > 14 ||
      minutes > 59 ||
      (h === 14 && minutes !== 0)
    )
      return false;
  }
  return Number.isFinite(Date.parse(value));
}
const text = (max: number) =>
  z
    .string()
    .min(1)
    .max(max)
    .refine((v) => v.trim() === v && !/[\u0000-\u001f\u007f]/.test(v));
const instant = z.string().refine(explicitInstant);
const sourceUrl = z
  .string()
  .max(2048)
  .refine((value) => {
    try {
      const parsed = new URL(value);
      return (
        ["http:", "https:"].includes(parsed.protocol) &&
        !parsed.username &&
        !parsed.password
      );
    } catch {
      return false;
    }
  });
const excerpt = z.string().trim().min(1).max(8000);
const stage = z.discriminatedUnion("status", [
  z
    .object({
      status: z.literal("KNOWN"),
      label: text(80),
      evidence_excerpt: excerpt,
    })
    .strict(),
  z.object({ status: z.literal("UNKNOWN") }).strict(),
]);
const deadline = z.discriminatedUnion("status", [
  z
    .object({
      status: z.literal("KNOWN"),
      at: instant,
      evidence_excerpt: excerpt,
    })
    .strict(),
  z
    .object({ status: z.literal("NOT_STATED"), evidence_excerpt: excerpt })
    .strict(),
  z.object({ status: z.literal("UNKNOWN") }).strict(),
]);
const schema = z
  .object({
    schema_version: z.literal(1),
    opportunity_id: text(128),
    source_url: sourceUrl,
    observed_at: instant,
    evidence_version: text(128),
    stage,
    materials_deadline: deadline,
  })
  .strict();
export type OpportunityLibraryFacts = z.infer<typeof schema>;
export type LibraryFactsState =
  | { status: "missing" }
  | { status: "invalid" }
  | { status: "ready"; facts: OpportunityLibraryFacts };

/** undefined = absent capability/data; null = supplied but invalid. */
export function decodeLibraryFacts(
  raw: unknown,
): OpportunityLibraryFacts | null | undefined {
  if (raw === undefined || raw === null) return undefined;
  const parsed = schema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}
export function libraryFactsFor(row: Opportunity): LibraryFactsState {
  if (row.libraryFacts === undefined) return { status: "missing" };
  const parsed = schema.safeParse(row.libraryFacts);
  if (!parsed.success) return { status: "invalid" };
  const facts = parsed.data;
  if (
    facts.opportunity_id !== row.id ||
    facts.source_url !== row.url ||
    facts.evidence_version !== row.sourceEvidenceVersion ||
    !row.sourceObservedAt ||
    !explicitInstant(row.sourceObservedAt) ||
    Date.parse(facts.observed_at) !== Date.parse(row.sourceObservedAt)
  )
    return { status: "invalid" };
  return { status: "ready", facts };
}
export const DEADLINE_FILTERS = {
  all: "全部",
  upcoming: "未截止",
  week: "7天内截止",
  overdue: "已截止",
  unstated: "来源未说明",
  missing: "尚未提供",
  unverified: "待核验",
} as const;
export type DeadlineFilter = keyof typeof DEADLINE_FILTERS;
export function deadlineFilter(value: string | null): DeadlineFilter {
  return value && Object.hasOwn(DEADLINE_FILTERS, value)
    ? (value as DeadlineFilter)
    : "all";
}
export function stageKey(row: Opportunity): string {
  const state = libraryFactsFor(row);
  if (state.status === "missing") return "missing";
  if (state.status === "invalid" || state.facts.stage.status === "UNKNOWN")
    return "unverified";
  return `known:${state.facts.stage.label}`;
}
export function deadlineAt(row: Opportunity): number | undefined {
  const state = libraryFactsFor(row);
  return state.status === "ready" &&
    state.facts.materials_deadline.status === "KNOWN"
    ? Date.parse(state.facts.materials_deadline.at)
    : undefined;
}
export function matchesLibraryFilters(
  row: Opportunity,
  selectedStage: string,
  selectedDeadline: DeadlineFilter,
  now: number,
): boolean {
  if (selectedStage !== "all" && selectedStage !== stageKey(row)) return false;
  const state = libraryFactsFor(row);
  if (selectedDeadline === "all") return true;
  if (selectedDeadline === "missing") return state.status === "missing";
  if (selectedDeadline === "unverified")
    return (
      state.status === "invalid" ||
      (state.status === "ready" &&
        state.facts.materials_deadline.status === "UNKNOWN")
    );
  if (state.status !== "ready") return false;
  const item = state.facts.materials_deadline;
  if (selectedDeadline === "unstated") return item.status === "NOT_STATED";
  if (item.status !== "KNOWN") return false;
  const at = Date.parse(item.at);
  if (selectedDeadline === "overdue") return at <= now;
  return (
    at > now && (selectedDeadline !== "week" || at <= now + 7 * 86_400_000)
  );
}
export function compareDeadlines(a: Opportunity, b: Opportunity): number {
  const left = deadlineAt(a),
    right = deadlineAt(b);
  if (left === undefined) return right === undefined ? 0 : 1;
  return right === undefined ? -1 : left - right;
}
export function deadlineText(at: string) {
  const match = /(Z|[+-]\d{2}:\d{2})$/.exec(at);
  const zone = match?.[1] === "Z" ? "UTC" : `UTC${match?.[1] || ""}`;
  const fullTime = at
    .replace(/(Z|[+-]\d{2}:\d{2})$/, "")
    .replace("T", " ")
    .replace(/:00$/, "");
  return {
    short: at.slice(5, 16).replace("T", " "),
    full: `${fullTime} ${zone}`,
    zone: `${at.slice(0, 4)} · ${zone}`,
  };
}
export function libraryExportFields(row: Opportunity): [string, string] {
  const state = libraryFactsFor(row);
  if (state.status !== "ready")
    return state.status === "missing"
      ? ["尚未提供", "尚未提供"]
      : ["待核验", "待核验"];
  const { stage, materials_deadline: deadline } = state.facts;
  return [
    stage.status === "KNOWN" ? stage.label : "待核验",
    deadline.status === "KNOWN"
      ? deadlineText(deadline.at).full
      : deadline.status === "NOT_STATED"
        ? "来源未说明"
        : "待核验",
  ];
}
