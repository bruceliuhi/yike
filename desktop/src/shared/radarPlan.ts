import { z } from 'zod';

const safeText = (value: string) => !/[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value);
const term = z.string().min(1).max(160).refine(value => value.trim().length > 0 && safeText(value));
export const radarPlanInputSchema = z.object({
  querySeeds: z.array(term).min(1).max(20),
  intentSignals: z.array(term).max(20),
  exclusions: z.array(term).max(25),
  region: z.string().max(80).refine(safeText),
  demandTypes: z.array(z.enum(['INQUIRY', 'COMPARISON', 'REPLACEMENT', 'CHANGE'])).max(4)
    .refine(items => new Set(items).size === items.length),
}).strict();
export const radarPlanRequestSchema = radarPlanInputSchema.extend({
  contractVersion: z.literal(1), requestId: z.string().uuid(),
}).strict();
const query = z.string().min(1).max(512).refine(safeText);
export const radarPlanSchema = z.object({
  version: z.string().min(1).max(128),
  strategies: z.array(z.object({
    id: z.enum(['quick', 'condition', 'broad']),
    name: z.string().min(1).max(80), purpose: z.string().min(1).max(240),
    queries: z.array(query).max(24),
  }).strict()).length(3).refine(items => new Set(items.map(item => item.id)).size === 3),
  queries: z.array(query).min(1).max(24),
}).strict().refine(plan => {
  const queries = new Set(plan.queries);
  const grouped = plan.strategies.flatMap(strategy => strategy.queries);
  const uniqueGrouped = new Set(grouped);
  return queries.size === plan.queries.length && uniqueGrouped.size === grouped.length &&
    queries.size === uniqueGrouped.size && grouped.every(value => queries.has(value));
});
export const radarPlanResponseSchema = z.object({
  contractVersion: z.literal(1), requestId: z.string().uuid(), userId: z.string().min(1),
  accountScope: z.object({ id: z.string().uuid(), version: z.literal(1) }).strict(),
  plan: radarPlanSchema,
}).strict();
export type RadarPlanInput = z.infer<typeof radarPlanInputSchema>;
export type RadarPlan = z.infer<typeof radarPlanSchema>;
