import { taskDraftOwner, taskDraftSchema } from "../../src/renderer/app/taskDraft";
import { EMPTY_PROFILE, newTaskDraft, type TaskDraft } from "../../src/renderer/domain/models";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import { ServiceError, type YikeService } from "../../src/renderer/services/contracts";
import { createRadarPlanService } from "../../src/renderer/services/radarPlan";
import { DYNAMIC_RESEARCH_SOURCE } from "../../src/shared/dynamicResearch";
import { radarPlanInputSchema, radarPlanRequestSchema, radarPlanSchema } from "../../src/shared/radarPlan";
import { RADAR_VISUAL_FIXTURES } from "../fixtures/radarPlanVisual";
import { TEST_TIME, TEST_USER } from "./fixtures";

const TEST_SCOPE = { id: "aa000000-0000-4000-8000-000000000006", version: 1 } as const;
const TEST_PROFILE = "bb000000-0000-4000-8000-000000000006";

/** Explicit TEST opt-in. Uses the real wizard/service validator with fixed in-memory responses only. */
export function configureRadarIntegrationVisual(
  service: YikeService,
  params: URLSearchParams,
  record: (operation: string, detail?: string) => void,
): { owner: string; draft: TaskDraft } | null {
  if (!params.has("radar")) return null;
  if (params.get("radar") !== "integrated" || params.get("scenario") !== "P06"
    || (params.has("state") && params.get("state") !== "populated")
    || [...params.keys()].some(key => !["scenario", "state", "radar"].includes(key) || params.getAll(key).length !== 1))
    throw new Error("TEST 搜索计划入口仅接受 scenario=P06、radar=integrated 与可选 state=populated。");

  const fixtures = RADAR_VISUAL_FIXTURES.map(fixture => ({
    name: fixture.name, input: radarPlanInputSchema.parse(fixture.input), plan: radarPlanSchema.parse(fixture.plan),
  }));
  const primary = fixtures[0];
  const originalSession = service.session;
  service.session = async () => {
    const session = await originalSession();
    return session.authenticated ? { ...session, accountScope: { ...TEST_SCOPE } } : session;
  };
  service.profiles = async () => [{
    id: TEST_PROFILE, version: 1, status: "CONFIRMED", businessName: "TEST 工业水泵服务",
    fields: { ...EMPTY_PROFILE, service: "TEST 工业水泵选型与供货", customer: "TEST 合成采购需求" },
    description: "TEST 合成业务画像，仅供完整页面验收，无真实客户数据",
  }];
  service.suggest = async (profileId, requestId, signal) => {
    signal?.throwIfAborted();
    record("radar.TEST-suggest", "TEST 固定建议；未调用模型");
    return { profileId, requestId, keywords: [...primary.input.querySeeds], exclusions: [...primary.input.exclusions] };
  };
  service.researchPlan = createRadarPlanService(async (operation, path, method, payload, signal) => {
    if (operation !== "researchPlan.preview" || path !== "/research-plan/preview" || method !== "POST")
      throw new ServiceError("TEST_ROUTE_REJECTED", "TEST 仅支持固定搜索计划预览路由");
    const session = await service.session();
    if (!session.authenticated || session.userId !== TEST_USER || session.accountScope?.id !== TEST_SCOPE.id)
      throw new ServiceError("UNAUTHORIZED", "TEST 请重新登录", 401);
    const { contractVersion: _version, requestId, ...input } = radarPlanRequestSchema.parse(payload);
    const fixture = fixtures.find(item => JSON.stringify(item.input) === JSON.stringify(input));
    record("radar.TEST-preview", fixture ? `TEST 固定计划：${fixture.name}` : "TEST 无匹配的固定计划");
    // Simulate a late response, deliberately leaving cancellation to the real service/UI guards.
    await new Promise(resolve => setTimeout(resolve, 800));
    const current = await service.session();
    if (!current.authenticated || current.userId !== session.userId || current.accountScope?.id !== TEST_SCOPE.id)
      throw new ServiceError("UNAUTHORIZED", "TEST 会话已变化", 401);
    if (signal?.aborted) record("radar.TEST-late-response", "TEST 过期响应，由真实服务拒绝");
    if (!fixture) throw new ServiceError("TEST_PLAN_NOT_FIXTURE",
      "TEST 当前条件没有固定计划，请使用工业水泵或离心水泵，保留默认需求类型与排除词；未执行搜索。");
    return { contractVersion: 1, requestId, userId: session.userId,
      accountScope: { ...TEST_SCOPE }, plan: structuredClone(fixture.plan) };
  });
  const draft = taskDraftSchema.parse({
    ...newTaskDraft(), id: "TEST-radar-integrated-draft", name: "TEST 工业水泵采购需求研究",
    profileId: TEST_PROFILE, profileVersion: 1, suggestionProfile: TEST_PROFILE,
    terms: primary.input.querySeeds.map((value, index) => ({ id: `TEST-seed-${index}`, value, origin: "manual", edited: true })),
    exclusions: primary.input.exclusions.map((value, index) => ({ id: `TEST-exclusion-${index}`, value, origin: "manual", edited: true })),
    source: "search", platforms: ["web"], publicSource: DYNAMIC_RESEARCH_SOURCE,
    executionLimits: { max_records: 20, max_runtime_seconds: 900 },
    research: { ...defaultResearchSettings(), demandTypes: primary.input.demandTypes, maxSoubei: 100,
      limits: { sources: 20, minutes: 15, modelCalls: 20 },
      dynamicScope: { version: 1, maxAgeDays: 60, timezone: "Asia/Shanghai" } },
    savedAt: TEST_TIME,
  });
  return { owner: taskDraftOwner(TEST_USER, TEST_SCOPE), draft };
}
