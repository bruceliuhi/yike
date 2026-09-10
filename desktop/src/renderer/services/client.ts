import { ServiceError, type YikeService } from "./contracts";
import { desktopDeviceIdentity } from './deviceIdentity';
import { desktopExecution } from './desktopExecution';
import {foregroundCollection, attachForegroundBinding} from './foregroundCollection';
import {monitorCollection} from './monitorCollection';
import {
  EMPTY_PROFILE,
  type Followup,
  type Opportunity,
  type Profile,
  type ProfileFields,
  type Session,
} from "../domain/models";
import type { YikeDesktopApi, ApiOperation } from "../../shared/contracts";
import { decodeLibraryFacts } from "../domain/opportunityLibrary";
import { decodeConnectionRegistry } from "./connectionRegistry";
import { createPlatformConnectionService } from "./platformConnection";
import { createResearchStrategiesService } from "./researchStrategies";
import { parseOpportunitySourceEvidence } from "../domain/opportunitySourceEvidence";
import { createCandidateReviewService, CANDIDATE_PLATFORM_LABELS } from "./candidateReview";
import { createMaterialsService } from "./materials";

type JsonRecord = Record<string, unknown>;
function bridge(): YikeDesktopApi | undefined {
  return (window as unknown as { yikeDesktop?: YikeDesktopApi }).yikeDesktop;
}
const text = (v: unknown): string => (typeof v === "string" ? v : "");
function record(value: unknown): JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}
function list(value: unknown): JsonRecord[] {
  if (!Array.isArray(value) || value.some(item =>
    item === null || typeof item !== "object" || Array.isArray(item) || Object.keys(item).length === 0,
  ))
    throw new ServiceError(
      "INVALID_SERVICE_RESPONSE",
      "数据读取未完成，请重试。当前不能确认列表为空。",
    );
  return value as JsonRecord[];
}
function readSession(r: JsonRecord): Session {
  const result: Session = {authenticated: r.authenticated === true, userId: text(r.user_id)};
  if (r.account_scope !== undefined) {
    const scope = record(r.account_scope);
    if (!result.authenticated || !result.userId ||
        typeof scope.id !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(scope.id) ||
        scope.version !== 1 || Object.keys(scope).some(key => key !== 'id' && key !== 'version'))
      throw new ServiceError('INVALID_SERVICE_RESPONSE', '客户空间尚未核实，请重新登录。');
    result.accountScope = {id: scope.id, version: scope.version};
  }
  return result;
}
function serviceFailure(status: number, body: unknown): ServiceError {
  const details = record(record(body).detail);
  const code =
    typeof body === "string" ? body : text(details.code) || `HTTP_${status}`;
  const messages: Record<number, string> = {
    401: "请先登录，再访问客户工作空间。",
    403: "当前账号没有此操作权限。",
    404: "记录不存在或已不可访问。",
    409: "内容已发生变化，请刷新后重试。",
    422: "请检查填写内容。",
    429: "操作过于频繁，请稍后再试。",
    501: "这项服务尚未接通，已保留你的输入。",
    502: "服务暂时无法连接，请稍后重试。",
    503: "服务暂时不可用，请稍后重试。",
  };
  const codes: Record<string, string> = {
    phone_auth_failed: "验证码无效或已过期，请重新核对或获取验证码。",
    SERVICE_NOT_CONFIGURED: "客户服务尚未连接；可以先准备本机草稿。",
    SERVICE_UNAVAILABLE: "客户服务暂时不可用，请稍后重试。",
    NETWORK_ERROR: "网络连接失败，当前输入已保留。",
    INVALID_REQUEST: "请求格式不正确，请检查当前填写内容。",
  };
  return new ServiceError(
    code,
    codes[code] || messages[status] || "操作未完成，请稍后重试。",
    status,
  );
}
async function requestRaw(
  operation: ApiOperation,
  path: string,
  method = "GET",
  payload?: unknown,
  signal?: AbortSignal,
): Promise<unknown> {
  const b = bridge();
  if (b?.requestApi) {
    const result = await b.requestApi({ operation, payload });
    if (!result.ok) throw serviceFailure(result.status, result.error);
    return result.data;
  }
  if (window.location.protocol === "yike:")
    throw new ServiceError(
      "SERVICE_NOT_CONFIGURED",
      "尚未连接客户服务，请在账号与授权中查看连接状态。",
    );
  try {
    const hasBody =
      payload !== undefined && method !== "GET" && method !== "HEAD";
    const response = await fetch(`/api/ui${path}`, {
      method,
      credentials: "same-origin",
      redirect: "error",
      headers: hasBody ? { "Content-Type": "application/json" } : undefined,
      body: hasBody ? JSON.stringify(payload) : undefined,
      signal,
    });
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) {
      if (!response.ok) throw serviceFailure(response.status, null);
      throw new ServiceError(
        "SERVICE_NOT_CONFIGURED",
        "客户服务尚未连接；可以先准备本机草稿。",
        response.status,
      );
    }
    const body: unknown = await response.json();
    if (!response.ok) throw serviceFailure(response.status, body);
    return body;
  } catch (error) {
    if (
      error instanceof ServiceError ||
      (error instanceof DOMException && error.name === "AbortError")
    )
      throw error;
    throw new ServiceError(
      "NETWORK_ERROR",
      "网络连接失败，输入已保留。请检查网络后重试。",
    );
  }
}
async function request(operation:ApiOperation,path:string,method='GET',payload?:unknown,signal?:AbortSignal):Promise<JsonRecord>{
  return record(await requestRaw(operation,path,method,payload,signal));
}
const labels: Record<keyof ProfileFields, string> = {
  service: "服务内容",
  customer: "目标客户",
  regions: "服务地区",
  preference: "项目偏好",
  exclusions: "排除项",
};
const profileStatuses = ["DRAFT", "CONFIRMED", "REVOKED"] as const;
function validProfileIdentifier(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 512 &&
    value.trim() === value &&
    !/[\u0000-\u001f\u007f]/.test(value)
  );
}
function invalidProfileResponse(): never {
  throw new ServiceError(
    "INVALID_SERVICE_RESPONSE",
    "画像列表响应不完整，请重新读取；未确认任何版本关系。",
  );
}
export function profileDescription(fields: ProfileFields): string {
  return (Object.keys(labels) as (keyof ProfileFields)[])
    .map((k) => `${labels[k]}：${JSON.stringify(fields[k])}`)
    .join("\n");
}
export function mapProfile(raw: JsonRecord): Profile {
  if (
    !validProfileIdentifier(raw.version_id) ||
    !Number.isSafeInteger(raw.version) ||
    (raw.version as number) <= 0 ||
    !profileStatuses.includes(raw.status as (typeof profileStatuses)[number]) ||
    (raw.profile_id !== undefined && !validProfileIdentifier(raw.profile_id))
  )
    invalidProfileResponse();
  const description = text(record(raw.payload).description);
  const fields = { ...EMPTY_PROFILE };
  for (const key of Object.keys(labels) as (keyof ProfileFields)[]) {
    const match = description
      .split("\n")
      .find((line) => line.startsWith(labels[key] + "："));
    const value = match ? match.slice(labels[key].length + 1) : "";
    try {
      const parsed: unknown = JSON.parse(value);
      fields[key] = typeof parsed === "string" ? parsed : value;
    } catch {
      fields[key] = value;
    }
  }
  if (!Object.values(fields).some(Boolean)) fields.service = description;
  return {
    id: raw.version_id,
    ...(raw.profile_id !== undefined
      ? { profileEntityId: raw.profile_id }
      : {}),
    version: raw.version as number,
    status: raw.status as Profile["status"],
    fields,
    description,
  };
}
function invalidEvidenceResponse(): never {
  throw new ServiceError(
    "INVALID_SERVICE_RESPONSE",
    "原文证据响应不完整，请重新读取。",
  );
}
export function mapOpportunity(r: JsonRecord): Opportunity {
  let sourceEvidence: Opportunity["sourceEvidence"];
  if (Object.hasOwn(r, "source_evidence")) {
    try {
      sourceEvidence = parseOpportunitySourceEvidence(r.source_evidence, {
        opportunityId: text(r.opportunity_id),
        profileVersionId: text(r.profile_version_id),
      });
    } catch {
      invalidEvidenceResponse();
    }
  }
  return {
    ...(sourceEvidence === undefined ? {} : { sourceEvidence }),
    sourceObservedAt: text(r.source_observed_at) || undefined,
    sourceEvidenceVersion: text(r.source_evidence_version) || undefined,
    libraryFacts: decodeLibraryFacts(r.library_facts),
    id: text(r.opportunity_id),
    title: text(r.title),
    buyer: text(r.buyer),
    summary: text(r.summary),
    excerpt: text(r.public_excerpt),
    matchReason: text(r.match_reason),
    actionSignal: text(r.action_signal),
    value: text(r.value_judgment),
    risk: text(r.risk),
    contactPath: text(r.contact_path),
    url: text(r.public_url),
    platform: text(r.source_platform),
    sourceStatus: text(r.source_status),
    profileStatus: text(r.profile_status),
    profileVersionId: text(r.profile_version_id),
    reviewer: text(r.reviewed_by),
    reviewedAt: text(r.reviewed_at),
    publishedAt: text(r.published_at),
    updatedAt: text(r.updated_at),
    intentStatus: text(r.intent_status),
    comment: text(r.draft_comment),
    dm: text(r.draft_dm),
  };
}
function mapFollowup(r: JsonRecord): Followup {
  return {
    id: text(r.followup_id),
    opportunityId: text(r.opportunity_id),
    title: text(r.title),
    status: text(r.status) as Followup["status"],
    note: text(r.note),
    createdAt: text(r.created_at),
    kind: "manual",
  };
}
function unavailable(name: string): never {
  throw new ServiceError(
    "CAPABILITY_UNAVAILABLE",
    `${name}尚未接通，已保留当前配置。`,
    501,
  );
}
const candidateReads = createCandidateReviewService(request);
const platformConnections = createPlatformConnectionService(bridge, () => service.connections());
export const service: YikeService = {
  materials: createMaterialsService(requestRaw),
  replyEvidence:(opportunityId,signal)=>requestRaw('replies.evidence',`/opportunities/${encodeURIComponent(opportunityId)}/replies/evidence`,'GET',{opportunityId},signal),
  get execution() { return desktopExecution(bridge()); },
  get foregroundCollection() { return foregroundCollection(bridge()); },
  get monitorCollection() { return monitorCollection(bridge()); },
  get deviceIdentity() { return desktopDeviceIdentity(bridge()); },
  candidateReview: candidateReads,
  researchStrategies: createResearchStrategiesService(request),
  rawCandidateEvidence: candidateReads.getRawEvidence,
  verifyContact: async () => unavailable("收件对象与发送条件核验"),
  candidates: async (query = {}, signal) => {
    const page = await candidateReads.list(query, signal);
    return {
      ...page,
      items: page.items.map((item) => ({
        ...item,
        platform: CANDIDATE_PLATFORM_LABELS[item.platform],
        sourceLabel: CANDIDATE_PLATFORM_LABELS[item.platform],
      })),
    };
  },
  // Real P07 writes use candidateReview + its durable request ledger; legacy implicit calls remain blocked.
  reviewCandidate: async () => unavailable("候选判断与人工复核"),
  session: async () => {
    const r = await request("session.get", "/session");
    return readSession(r);
  },
  loginToken: async (token) => {
    const r = await request("session.login", "/session", "POST", { token });
    return readSession(r);
  },
  logout: async () => {
    await request("session.logout", "/session", "DELETE");
  },
  requestCode: async (phone) => {
    const r = await request("session.requestCode", "/auth/sms-code", "POST", {phone});
    if (typeof r.retry_after !== "number" || !Number.isInteger(r.retry_after) || r.retry_after < 1 || r.retry_after > 300)
      throw new ServiceError("INVALID_SERVICE_RESPONSE", "验证码服务响应无效，请稍后重试。");
    return {retryAfter: r.retry_after};
  },
  login: async (phone, code, trial) => {
    const r = await request("session.loginPhone", "/auth/sms-session", "POST", {
      phone, code, ...(trial === undefined ? {} : {trial_code: trial}),
    });
    if (r.authenticated !== true || typeof r.user_id !== "string" || !r.user_id.trim())
      throw new ServiceError("INVALID_SERVICE_RESPONSE", "登录状态尚未核实，请稍后重试。");
    return readSession(r);
  },
  profiles: async () =>
    list((await request("profiles.list", "/profiles")).items).map(mapProfile),
  saveProfile: async (fields) => {
    const description = profileDescription(fields);
    const r = await request("profiles.save", "/profiles", "POST", {
      description,
    });
    return mapProfile({ ...r, payload: { description } });
  },
  confirmProfile: async (id) =>
    mapProfile(
      await request(
        "profiles.confirm",
        `/profiles/${encodeURIComponent(id)}/confirm`,
        "POST",
        { version_id: id },
      ),
    ),
  opportunities: async () =>
    list((await request("opportunities.list", "/opportunities")).items).map(
      mapOpportunity,
    ),
  opportunity: async (id, signal) => {
    signal?.throwIfAborted();
    const response = await request(
      "opportunities.get",
      `/opportunities/${encodeURIComponent(id)}`,
      "GET",
      { id },
      signal,
    );
    // The native bridge has no cancellation protocol: never adopt its late reply.
    signal?.throwIfAborted();
    const raw = record(response.opportunity);
    if (raw.opportunity_id !== id || !Object.hasOwn(raw, "source_evidence"))
      invalidEvidenceResponse();
    return mapOpportunity(raw);
  },
  followups: async () =>
    list((await request("followups.list", "/followups")).items).map(
      mapFollowup,
    ),
  addFollowup: async (id, status, note) => {
    const receipt = await request("followups.add", "/followups", "POST", {
      opportunity_id: id,
      status,
      note,
    });
    if (!validProfileIdentifier(receipt.followup_id))
      throw new ServiceError(
        "INVALID_SERVICE_RESPONSE",
        "保存回执不完整，结果尚未确认。输入与原请求保护已保留，请核对已有登记，不要重复保存。",
      );
  },
  connections: async () => {
    const api = foregroundCollection(bridge());
    const [raw, capability] = await Promise.all([request("connections.list", "/connections"),
      api ? api.execute({action:'CAPABILITIES'}) : Promise.resolve({state:'UNAVAILABLE'} as const)]);
    return attachForegroundBinding(decodeConnectionRegistry(raw), capability);
  },
  connect: platformConnections.connect,
  checkConnection: platformConnections.checkConnection,
  cancelConnection: platformConnections.cancelConnection,
  disconnect: async () => unavailable("断开连接"),
  suggest: async () => unavailable("AI 搜索建议"),
  tasks: async () => unavailable("任务运行服务"),
  startTask: async () => unavailable("任务启动"),
  taskAction: async () => unavailable("任务操作"),
  generateContact: async () => unavailable("联系草稿生成"),
  saveContact: async () => unavailable("草稿同步"),
  send: async () => unavailable("消息发送"),
  activate: async () => unavailable("产品激活"),
  checkUpdate: async () => unavailable("更新检查"),
  info: async () => {
    const desktop = bridge();
    if (desktop) {
      const api = foregroundCollection(desktop);
      const [info, runtime, capability] = await Promise.all([desktop.getClientInfo(), desktop.getRuntimeStatus(),
        api ? api.execute({action:'CAPABILITIES'}) : Promise.resolve({state:'UNAVAILABLE'} as const)]);
      return { ...info, deviceReady: runtime.state === "READY" || capability.state === 'AVAILABLE' };
    }
    let serviceConfigured = false;
    try {
      await request("capabilities.get", "/capabilities");
      serviceConfigured = true;
    } catch {}
    return {
      version: "0.2.0",
      platform: "浏览器",
      serviceConfigured,
      deviceReady: false,
    };
  },
  openExternal: async (url) => {
    const parsed = new URL(url);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password
    )
      throw new ServiceError("UNSAFE_URL", "仅支持公开网页链接。");
    const desktop = bridge();
    if (desktop) {
      const result = await desktop.openExternal(url);
      if (!result.ok)
        throw new ServiceError(
          result.error,
          "未能打开来源链接，请复制后在浏览器中打开。",
        );
      return;
    }
    if (window.location.protocol === "yike:")
      throw new ServiceError(
        "EXTERNAL_LINK_UNAVAILABLE",
        "请复制来源链接，在浏览器中打开。",
      );
    window.open(parsed.href, "_blank", "noopener,noreferrer");
  },
  copy: async (value) => {
    const desktop = bridge();
    if (desktop) {
      const result = await desktop.copyText(value);
      if (!result.ok)
        throw new ServiceError(
          result.error,
          "复制未完成，请选中文字手动复制。",
        );
      return;
    }
    if (!navigator.clipboard)
      throw new ServiceError(
        "CLIPBOARD_UNAVAILABLE",
        "无法访问剪贴板，请选中文字手动复制。",
      );
    await navigator.clipboard.writeText(value);
  },
};
