import { ServiceError, type YikeService } from "./contracts";
import {
  EMPTY_PROFILE,
  type Followup,
  type Opportunity,
  type Profile,
  type ProfileFields,
} from "../domain/models";
import type { YikeDesktopApi, ApiOperation } from "../../shared/contracts";

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
  return Array.isArray(value) ? value.map(record) : [];
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
async function request(
  operation: ApiOperation,
  path: string,
  method = "GET",
  payload?: unknown,
  signal?: AbortSignal,
): Promise<JsonRecord> {
  const b = bridge();
  if (b?.requestApi) {
    const result = await b.requestApi({ operation, payload });
    if (!result.ok) throw serviceFailure(result.status, result.error);
    return record(result.data);
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
    return record(body);
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
const labels: Record<keyof ProfileFields, string> = {
  service: "服务内容",
  customer: "目标客户",
  regions: "服务地区",
  preference: "项目偏好",
  exclusions: "排除项",
};
export function profileDescription(fields: ProfileFields): string {
  return (Object.keys(labels) as (keyof ProfileFields)[])
    .map((k) => `${labels[k]}：${JSON.stringify(fields[k])}`)
    .join("\n");
}
export function mapProfile(raw: JsonRecord): Profile {
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
    id: text(raw.version_id),
    version: Number(raw.version) || 1,
    status: (["DRAFT", "CONFIRMED", "REVOKED"].includes(text(raw.status))
      ? raw.status
      : "DRAFT") as Profile["status"],
    fields,
    description,
  };
}
export function mapOpportunity(r: JsonRecord): Opportunity {
  return {
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
export const service: YikeService = {
  verifyContact: async () => unavailable("收件对象与发送条件核验"),
  candidates: async () => unavailable("原始候选读取"),
  reviewCandidate: async () => unavailable("候选判断与人工复核"),
  session: async () => {
    const r = await request("session.get", "/session");
    return { authenticated: r.authenticated === true, userId: text(r.user_id) };
  },
  loginToken: async (token) => {
    const r = await request("session.login", "/session", "POST", { token });
    return { authenticated: r.authenticated === true, userId: text(r.user_id) };
  },
  logout: async () => {
    await request("session.logout", "/session", "DELETE");
  },
  requestCode: async () => unavailable("短信验证码服务"),
  login: async () => unavailable("手机号登录服务"),
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
  opportunity: async (id) =>
    mapOpportunity(
      record(
        (
          await request(
            "opportunities.get",
            `/opportunities/${encodeURIComponent(id)}`,
            "GET",
            { id },
          )
        ).opportunity,
      ),
    ),
  followups: async () =>
    list((await request("followups.list", "/followups")).items).map(
      mapFollowup,
    ),
  addFollowup: async (id, status, note) => {
    await request("followups.add", "/followups", "POST", {
      opportunity_id: id,
      status,
      note,
    });
  },
  connections: async () => unavailable("平台连接"),
  connect: async () => unavailable("平台登录"),
  checkConnection: async () => unavailable("连接检查"),
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
      const info = await desktop.getClientInfo();
      const runtime = await desktop.getRuntimeStatus();
      return { ...info, deviceReady: runtime.state === "READY" };
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
