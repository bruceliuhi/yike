import {z} from 'zod';
import {strategyUuidSchema} from './researchStrategies';

const id = z.string().refine(v => v.trim() === v && v.length > 0 && Array.from(v).length <= 512
  && !/[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(v));
const count = z.number().int().positive().max(1000000);
const sha = z.string().length(64).regex(/^[a-f0-9]{64}$/);
export const confirmedResearchBindingSchema = z.object({
  strategyVersionId: strategyUuidSchema, profileVersionId: strategyUuidSchema, configurationSha256: sha,
}).strict();
export type ConfirmedResearchBinding = z.infer<typeof confirmedResearchBindingSchema>;
/** Only the confirmed-version contract may cross the real HTTP/IPC boundary. */
export const researchUsageRequestSchema = z.object({
  contractVersion: z.literal(1), requestId: strategyUuidSchema, userId: id, accountScopeId: id,
  accountScopeVersion: z.literal(1), draftId: id, revision: count, configurationHash: sha, maxSoubei: count,
  strategyBinding: confirmedResearchBindingSchema,
}).strict();
export const researchUsageResponseSchema = researchUsageRequestSchema.extend({
  quoteId: strategyUuidSchema, ruleVersion: id, ruleSha256: sha,
  authorizationToken: z.string().min(1).max(8192), estimatedSoubei: z.number().finite().nonnegative().max(1000000),
  generatedAt: z.string().datetime({offset: true}), expiresAt: z.string().datetime({offset: true}),
  basis: z.string().min(1).max(2000).refine(v => v.trim().length > 0),
}).strict();
