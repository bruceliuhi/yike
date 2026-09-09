import type {
  ContactDraft,
  PlatformConnection,
  Suggestion,
  TaskDraft,
} from "../../src/renderer/domain/models";
import type {
  SendReceipt,
  SendRequestBinding,
} from "../../src/renderer/domain/outreach";
import {
  configurationHash,
  type TaskStartBinding,
  type TaskStartReceipt,
} from "../../src/renderer/domain/taskOperations";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
import { TEST_USER, opportunity, profile, taskDraft } from "./fixtures";

export const RECOVERY_SCENARIOS = [
  "ai-late",
  "send-unknown",
  "start-unknown",
  "connection-limited",
] as const;
export type RecoveryScenario = (typeof RECOVERY_SCENARIOS)[number];
const pages: Record<RecoveryScenario, string[]> = {
  "ai-late": ["P06", "P20"],
  "send-unknown": ["P13"],
  "start-unknown": ["P19"],
  "connection-limited": ["P17"],
};
export function selectRecovery(
  value: string | null,
  page: string,
  state: string,
  guest: boolean,
): RecoveryScenario | undefined {
  if (!value) return;
  if (
    !(RECOVERY_SCENARIOS as readonly string[]).includes(value) ||
    !pages[value as RecoveryScenario]?.includes(page) ||
    state !== "populated" ||
    guest
  )
    throw new Error(
      "TEST 恢复场景参数不匹配：只接受文档列出的页面、populated 和 TEST 登录身份。",
    );
  return value as RecoveryScenario;
}
export interface RecoverySnapshot {
  name: RecoveryScenario;
  pendingSuggestions: number;
  originalRequest: string;
  phase: "READY" | "WAITING" | "UNKNOWN" | "CONFIRMED_NOT_EXECUTED";
}
export interface RecoveryController {
  name: RecoveryScenario;
  seed(storage: Storage, page: string): void;
  subscribe(listener: () => void): () => void;
  snapshot(): RecoverySnapshot;
  releaseSuggestions(): void;
  confirmNotExecuted(): void;
}
const ACCOUNT = "TEST-recovery-account";
const RECIPIENT = "TEST-recovery-recipient";
const TOKEN_PREFIX = "TEST-IN-MEMORY-PROOF:";
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, canonical(item)]),
    );
  return value;
}
const same = (left: unknown, right: unknown) =>
  JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));

/** Opt-in TEST-only transport states. Never creates a run, sends a message, or calls external IO. */
export function configureRecovery(
  harness: {
    service: YikeService;
    record(operation: string, detail?: string): void;
  },
  name: RecoveryScenario,
): RecoveryController {
  const { service, record } = harness;
  const listeners = new Set<() => void>();
  let state: RecoverySnapshot = {
    name,
    pendingSuggestions: 0,
    originalRequest: "",
    phase: "READY",
  };
  const update = (change: Partial<RecoverySnapshot>) => {
    state = { ...state, ...change };
    listeners.forEach((fn) => fn());
  };
  const requireUser = async () => {
    const current = await service.session();
    if (!current.authenticated || current.userId !== TEST_USER)
      throw new ServiceError(
        "UNAUTHORIZED",
        "TEST 恢复场景仅接受本实例的测试身份",
        401,
      );
  };
  const reject = (message: string): never => {
    throw new ServiceError("VISUAL_SCOPE_REJECTED", "TEST " + message, 400);
  };
  const requireDraft = (draft: ContactDraft) => {
    if (
      draft.opportunityId !== opportunity.id ||
      draft.accountId !== ACCOUNT ||
      draft.recipient !== RECIPIENT ||
      !["comment", "dm"].includes(draft.channel) ||
      !draft.content.includes("TEST") ||
      draft.content !== draft.savedContent ||
      !Number.isSafeInteger(draft.version) ||
      draft.version < 1
    )
      reject("发送草稿不属于本场景的合成对象或未保存内容");
  };
  const connection: PlatformConnection = {
    platform: "xhs",
    status: "CONNECTED",
    accountId: ACCOUNT,
    accountName: "TEST 内存账号（并未真实登录）",
    capabilities: ["search", "read", "monitor", "comment", "dm"],
    reason: "TEST 条件夹具；不代表真实平台支持",
  };
  const pendingSuggestions: Array<{
    profileId: string;
    requestId: string;
    finish(value: Suggestion): void;
  }> = [];
  let sendOriginal:
    { binding: SendRequestBinding; draft: ContactDraft } | undefined;
  let startOriginal: TaskStartBinding | undefined;
  const proofs = new Map<
    string,
    { draft: ContactDraft; fingerprint: string; expiresAt: string }
  >();
  let loginOpened = false;
  let loginChecked = false;
  const sendReceipt = (): SendReceipt => {
    if (!sendOriginal) return reject("没有已记录的原发送请求");
    return state.phase === "CONFIRMED_NOT_EXECUTED"
      ? {
          ...sendOriginal.binding,
          status: "FAILED",
          confirmed: true,
          confirmedNotDelivered: true,
        }
      : { ...sendOriginal.binding, status: "UNKNOWN" };
  };
  const startReceipt = (): TaskStartReceipt => {
    if (!startOriginal) return reject("没有已记录的原启动请求");
    return state.phase === "CONFIRMED_NOT_EXECUTED"
      ? {
          ...startOriginal,
          status: "REJECTED",
          confirmedNotStarted: true,
          message: "TEST 原请求确认未创建任务；没有执行器运行。",
        }
      : {
          ...startOriginal,
          status: "UNKNOWN",
          message: "TEST 原启动结果未知；未运行执行器。",
        };
  };

  if (name === "ai-late") {
    service.suggest = async (profileId, requestId) => {
      await requireUser();
      if (profileId !== profile.id || !requestId)
        return reject("建议请求画像不匹配");
      record("recovery.suggest.wait", "TEST 延迟建议；未调用模型");
      return new Promise<Suggestion>((finish) => {
        // Deliberately ignore AbortSignal: releasing after cancellation also
        // exercises the production component's stale-response protection.
        pendingSuggestions.push({ profileId, requestId, finish });
        update({
          pendingSuggestions: pendingSuggestions.length,
          phase: "WAITING",
        });
      });
    };
  }
  if (name === "send-unknown" || name === "start-unknown") {
    service.connections = async () => structuredClone([connection]);
  }
  if (name === "send-unknown") {
    const queue = service.outreach!.queue;
    service.verifyContact = async (draft, fingerprint) => {
      await requireUser();
      requireDraft(draft);
      const token = TOKEN_PREFIX + crypto.randomUUID();
      const expiresAt = new Date(Date.now() + 600_000).toISOString();
      proofs.set(token, {
        draft: structuredClone(draft),
        fingerprint,
        expiresAt,
      });
      record("recovery.send.verify", "TEST 内存条件；没有查询真实对象");
      return {
        allowed: true,
        fingerprint,
        confirmationToken: token,
        expiresAt,
        opportunityId: opportunity.id,
        accountId: ACCOUNT,
        channel: draft.channel,
        recipientId: RECIPIENT,
        recipientLabel: "TEST 合成收件人（不会实际发送）",
      };
    };
    service.outreach = {
      queue,
      send: async (draft, request) => {
        await requireUser();
        requireDraft(draft);
        const proof = proofs.get(request.confirmationToken);
        if (
          !proof ||
          !same(proof.draft, draft) ||
          Date.parse(proof.expiresAt) <= Date.now() ||
          !request.requestId ||
          request.requestId.length > 128
        )
          return reject("缺少本次草稿的有效 TEST 核验");
        const binding: SendRequestBinding = {
          requestId: request.requestId,
          opportunityId: opportunity.id,
          channel: draft.channel,
          version: draft.version,
        };
        if (
          sendOriginal &&
          (!same(sendOriginal.binding, binding) ||
            !same(sendOriginal.draft, draft))
        )
          return reject("已记录一个原请求，禁止建立第二个测试发送");
        sendOriginal = { binding, draft: structuredClone(draft) };
        record("recovery.send.unknown", "TEST 只记录原请求，未产生消息投递");
        if (state.phase !== "CONFIRMED_NOT_EXECUTED")
          update({ originalRequest: binding.requestId, phase: "UNKNOWN" });
        return sendReceipt();
      },
      reconcile: async (binding) => {
        await requireUser();
        if (!sendOriginal || !same(sendOriginal.binding, binding))
          return reject("核对参数与原发送请求不一致");
        record("recovery.send.reconcile", "TEST 仅查询本实例原请求");
        return sendReceipt();
      },
    };
  }
  if (name === "start-unknown") {
    const readInfo = service.info;
    service.info = async () => ({
      ...(await readInfo()),
      deviceReady: true,
      platform: "TEST 内存执行条件（无执行器）",
    });
    const unavailable = async (): Promise<never> => {
      throw new ServiceError(
        "CAPABILITY_UNAVAILABLE",
        "TEST 本场景不运行任务或执行任务操作",
        501,
      );
    };
    service.taskOperations = {
      start: async (draft, binding) => {
        await requireUser();
        if (
          !draft.id.startsWith("TEST-") ||
          !draft.name.includes("TEST") ||
          draft.profileId !== profile.id ||
          draft.profileVersion !== profile.version ||
          draft.platforms.length !== 1 ||
          draft.platforms[0] !== "xhs" ||
          draft.accounts.xhs !== ACCOUNT ||
          !draft.terms.length ||
          binding.draftId !== draft.id ||
          binding.revision !== draft.revision ||
          binding.mode !== draft.mode ||
          binding.requestId !== `task:${draft.id}:${draft.revision}` ||
          binding.configurationHash !== (await configurationHash(draft))
        )
          return reject("启动范围或配置摘要不匹配");
        if (startOriginal && !same(startOriginal, binding))
          return reject("已记录原启动请求，禁止建立第二个测试启动");
        startOriginal = structuredClone(binding);
        record(
          "recovery.start.unknown",
          "TEST 只记录启动请求，没有创建任务或运行执行器",
        );
        if (state.phase !== "CONFIRMED_NOT_EXECUTED")
          update({ originalRequest: binding.requestId, phase: "UNKNOWN" });
        return startReceipt();
      },
      reconcileStart: async (binding) => {
        await requireUser();
        if (!startOriginal || !same(startOriginal, binding))
          return reject("核对参数与原启动请求不一致");
        record("recovery.start.reconcile", "TEST 仅查询本实例原启动请求");
        return startReceipt();
      },
      task: unavailable,
      action: unavailable,
      reconcileAction: unavailable,
    };
  }
  if (name === "connection-limited") {
    const readConnections = service.connections;
    const limited: PlatformConnection = {
      ...connection,
      capabilities: [],
      reason: "TEST 登录状态存在但没有验证任何采集或触达能力",
    };
    service.connections = async () => {
      const rows = await readConnections();
      return rows.map((row) =>
        row.platform === "xhs" && loginChecked ? structuredClone(limited) : row,
      );
    };
    service.connect = async (platform) => {
      await requireUser();
      if (platform !== "xhs") return reject("只演示 TEST 小红书连接");
      loginOpened = true;
      record("recovery.connection.open", "TEST 内存阶段推进；未打开平台窗口");
      update({ phase: "WAITING" });
    };
    service.checkConnection = async (platform) => {
      await requireUser();
      if (platform !== "xhs" || !loginOpened)
        return reject("请先推进 TEST 打开窗口步骤");
      loginChecked = true;
      record(
        "recovery.connection.limited",
        "TEST 没有真实登录，返回空能力列表",
      );
      update({ phase: "READY" });
      return structuredClone(limited);
    };
  }
  return {
    name,
    seed(storage, page) {
      const draft: TaskDraft = taskDraft(page === "P20" ? "monitor" : "once");
      if (name === "ai-late")
        Object.assign(draft, {
          terms: [],
          exclusions: [],
          savedAt: null,
          suggestionProfile: null,
        });
      if (name === "start-unknown")
        Object.assign(draft, {
          platforms: ["xhs"],
          accounts: { xhs: ACCOUNT },
        });
      if (name === "ai-late" || name === "start-unknown")
        storage.setItem(
          `yike.ui.draft.v1.task.${TEST_USER}`,
          JSON.stringify(draft),
        );
      if (name === "send-unknown") {
        const contact = (channel: "comment" | "dm"): ContactDraft => ({
          opportunityId: opportunity.id,
          channel,
          content: opportunity[channel],
          savedContent: opportunity[channel],
          version: 2,
          accountId: ACCOUNT,
          recipient: RECIPIENT,
        });
        storage.setItem(
          `yike.ui.draft.v1.contact:${TEST_USER}:${opportunity.id}`,
          JSON.stringify({ comment: contact("comment"), dm: contact("dm") }),
        );
      }
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    snapshot: () => state,
    releaseSuggestions() {
      const pending = pendingSuggestions.splice(0);
      pending.forEach(({ profileId, requestId, finish }) =>
        finish({
          profileId,
          requestId,
          keywords: ["TEST 后到展台需求建议"],
          exclusions: ["TEST 后到排除建议"],
        }),
      );
      record(
        "recovery.suggest.release",
        `TEST 返回 ${pending.length} 条等待响应（含可能已取消请求）`,
      );
      update({ pendingSuggestions: 0, phase: "READY" });
    },
    confirmNotExecuted() {
      if (!sendOriginal && !startOriginal)
        return reject("尚无原请求，不能注入终态");
      record(
        "recovery.confirm-not-executed",
        "TEST 将原请求设为确定未执行；仍需在产品界面主动核对才能解除本机保护",
      );
      update({ phase: "CONFIRMED_NOT_EXECUTED" });
    },
  };
}
