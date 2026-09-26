import type { ApiOperation } from '../../shared/contracts';
import { radarPlanInputSchema, radarPlanResponseSchema, type RadarPlan, type RadarPlanInput } from '../../shared/radarPlan';
import type { Session } from '../domain/models';
import { ServiceError } from './contracts';

type Transport = (operation: ApiOperation, path: string, method?: string, payload?: unknown, signal?: AbortSignal) => Promise<unknown>;
export interface RadarPlanService {
  preview(input: RadarPlanInput, session: Session, signal?: AbortSignal): Promise<RadarPlan>;
}

export function createRadarPlanService(transport: Transport): RadarPlanService {
  return {
    async preview(input, session, signal) {
      signal?.throwIfAborted();
      if (!session.authenticated || !session.userId || !session.accountScope)
        throw new ServiceError('PLAN_SESSION_REQUIRED', '请登录后查看搜索计划。');
      const body = { ...radarPlanInputSchema.parse(input), contractVersion: 1, requestId: crypto.randomUUID() };
      const raw = await transport('researchPlan.preview', '/research-plan/preview', 'POST', body, signal);
      signal?.throwIfAborted();
      const parsed = radarPlanResponseSchema.safeParse(raw);
      if (!parsed.success || parsed.data.requestId !== body.requestId || parsed.data.userId !== session.userId ||
          parsed.data.accountScope.id !== session.accountScope.id || parsed.data.accountScope.version !== session.accountScope.version)
        throw new ServiceError('INVALID_PLAN_RESPONSE', '搜索计划未能核对，请重新查看。');
      return parsed.data.plan;
    },
  };
}
