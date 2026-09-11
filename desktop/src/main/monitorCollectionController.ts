import { randomUUID } from "node:crypto";
import { z } from "zod";
import {monitorSupportSchema as supportSchema} from "../shared/foregroundCollection";
import {
  executionOperationSchema,
  type ExecutionOperation,
} from "../shared/executionOperation";
import { parseExecutionReceipt } from "../shared/executionReceipt";
import {
  monitorCollectionCommandSchema,
  monitorScheduleSchema,
  type MonitorCollectionCommand,
  type MonitorCollectionPlan,
  type MonitorCollectionResult,
} from "../shared/monitorCollection";
import { deviceUuidSchema as uuid } from "../shared/deviceRegistration";
import type { DeviceWorkerScope } from "./deviceIdentityController";
const revision = z.number().int().min(1).max(2_147_483_647);
const planSchema = z
  .object({
    plan_id: uuid,
    profile_version_id: uuid,
    strategy_version_id: uuid,
    configuration_sha256: z
      .string()
      .length(64)
      .regex(/^[0-9a-f]{64}$/),
    schedule: monitorScheduleSchema,
    state: z.enum(["ACTIVE", "PAUSED"]),
    revision,
    next_due_at: z.string().datetime({ offset: true }).nullable(),
    execution_status: z.literal("NOT_CONNECTED"),
  })
  .strict();
const listSchema = z
  .object({
    schema_version: z.literal("monitor-plans-v1"),
    plans: z.array(planSchema).max(20),
    execution_status: z.literal("NOT_CONNECTED"),
  })
  .strict();
const receiptSchema = z
  .object({
    schema_version: z.literal("monitor-plans-v1"),
    request_id: uuid,
    operation: z.enum(["CREATE", "SET_STATE"]),
    plan: planSchema,
    recorded_at: z.string().datetime({ offset: true }),
  })
  .strict();

const occurrenceSchema = z
  .object({
    id: uuid,
    scheduled_at: z.string().datetime({ offset: true }),
    expires_at: z.string().datetime({ offset: true }),
    start_request: executionOperationSchema,
    task_id: uuid.nullable(),
  })
  .strict();
const pulseSchema = z
  .object({
    schema_version: z.literal("monitor-runtime-v1"),
    plan_id: uuid,
    plan_revision: revision,
    state: z.enum([
      "WAITING",
      "READY",
      "RUNNING",
      "RECOVERY_REQUIRED",
      "SKIPPED_OFFLINE",
      "SKIPPED_MISSED",
      "SKIPPED_BUSY",
    ]),
    server_time: z.string().datetime({ offset: true }),
    next_due_at: z.string().datetime({ offset: true }).nullable(),
    occurrence: occurrenceSchema.nullable(),
  })
  .strict();
type Plan = z.infer<typeof planSchema>;
type Target = NonNullable<ExecutionOperation["targets"]>[number];
type Attachment = {
  planId: string;
  revision: number;
  profileId: string;
  strategyId: string;
  configurationSha256: string;
  targets: Target[];
  userId: string;
  sessionId: string;
  deviceId: string;
  credentialVersion: number;
  monitorSessionId: string;
  taskId: string | null;
  lastError: string | null;
  running: boolean;
  stopping: boolean;
  stopUnconfirmed: boolean;
};
interface Options {
  identity: {
    openWorkerScope(): Promise<
      { ok: true; scope: DeviceWorkerScope } | { ok: false; state: string }
    >;
    getStatus(): unknown;
  };
  foreground: {
    canStart(): boolean;
    validateMonitorBinding(
      profileId: string,
      strategyId: string,
      targets: Target[],
    ): Promise<boolean>;
    startMonitor(start: unknown): Promise<unknown>;
    cancel(taskId?: string): void;
    stop?(taskId?: string): Promise<void>;
  };
  intervalMs?: number;
  autoStart?: boolean;
}
const same = (a: unknown, b: unknown) =>
  JSON.stringify(a) === JSON.stringify(b);
export function createMonitorCollectionController(options: Options) {
  const attached = new Map<string, Attachment>();
  let ticking = false,
    closed = false,
    generation = 0,
    fairCursor = 0;
  let timer: ReturnType<typeof setInterval> | undefined;
  const current = (
    scope: DeviceWorkerScope,
    token: number,
    local?: Attachment,
  ) =>
    !closed &&
    token === generation &&
    scope.session.isCurrent() &&
    (!local ||
      (attached.get(local.planId) === local &&
        scope.session.userId === local.userId &&
        scope.session.sessionId === local.sessionId &&
        scope.device.deviceId === local.deviceId &&
        scope.device.credentialVersion === local.credentialVersion));
  const stopExact = async (local: Attachment) => {
    if (!local.taskId) return;
    if (options.foreground.stop) await options.foreground.stop(local.taskId);
    else options.foreground.cancel(local.taskId);
  };
  async function open(token: number) {
    if (closed || token !== generation) return null;
    const result = await options.identity.openWorkerScope();
    if (!result.ok || !current(result.scope, token)) {
      if (result.ok) result.scope.close();
      return null;
    }
    return result.scope;
  }
  async function support(scope: DeviceWorkerScope, token: number) {
    const result = await scope.transport.requestExecution({
      operation: "monitor.support",
    });
    if (!current(scope, token)) throw new Error();
    const parsed = result.ok ? supportSchema.safeParse(result.data) : null;
    return !!parsed?.success && parsed.data.mode !== null;
  }
  async function plans(scope: DeviceWorkerScope, token: number) {
    const result = await scope.transport.requestExecution({
      operation: "monitor.list",
    });
    if (!current(scope, token)) throw new Error();
    if (!result.ok) throw new Error();
    return listSchema.parse(result.data).plans;
  }
  function published(plan: Plan, local?: Attachment): MonitorCollectionPlan {
    return {
      planId: plan.plan_id,
      profileVersionId: plan.profile_version_id,
      strategyVersionId: plan.strategy_version_id,
      configurationSha256: plan.configuration_sha256,
      schedule: plan.schedule,
      state: plan.state,
      revision: plan.revision,
      nextDueAt: plan.next_due_at,
      localState: local
        ? local.stopUnconfirmed
          ? "STOP_UNCONFIRMED"
          : local.stopping
            ? "STOPPING"
            : local.running
              ? "RUNNING"
              : "ATTACHED"
        : "DETACHED",
      taskId: local?.taskId ?? null,
      lastError: local?.lastError ?? null,
    };
  }
  async function attach(
    scope: DeviceWorkerScope,
    token: number,
    plan: Plan,
    targets: Target[],
  ) {
    if (
      plan.state !== "ACTIVE" ||
      !(await options.foreground.validateMonitorBinding(
        plan.profile_version_id,
        plan.strategy_version_id,
        targets,
      )) ||
      !current(scope, token)
    )
      return null;
    const value: Attachment = {
      planId: plan.plan_id,
      revision: plan.revision,
      profileId: plan.profile_version_id,
      strategyId: plan.strategy_version_id,
      configurationSha256: plan.configuration_sha256,
      targets: structuredClone(targets),
      userId: scope.session.userId,
      sessionId: scope.session.sessionId,
      deviceId: scope.device.deviceId,
      credentialVersion: scope.device.credentialVersion,
      monitorSessionId: randomUUID(),
      taskId: null,
      lastError: null,
      running: false,
      stopping: false,
      stopUnconfirmed: false,
    };
    if (!current(scope, token)) return null;
    attached.set(plan.plan_id, value);
    return value;
  }
  function validReceipt(
    command: Extract<
      MonitorCollectionCommand,
      { action: "CREATE" | "SET_STATE" }
    >,
    receipt: z.infer<typeof receiptSchema>,
  ) {
    if (receipt.request_id !== command.requestId) return false;
    return command.action === "CREATE"
      ? receipt.operation === "CREATE" &&
          receipt.plan.plan_id === command.requestId &&
          receipt.plan.profile_version_id === command.profileVersionId &&
          receipt.plan.strategy_version_id === command.strategyVersionId &&
          receipt.plan.state === "ACTIVE" &&
          receipt.plan.revision === 1
      : receipt.operation === "SET_STATE" &&
          receipt.plan.plan_id === command.planId &&
          receipt.plan.state === command.state &&
          receipt.plan.revision === command.expectedRevision + 1;
  }
  const controller = {
    async execute(raw: unknown): Promise<MonitorCollectionResult> {
      if (closed) return { state: "SERVICE_UNAVAILABLE" };
      const parsed = monitorCollectionCommandSchema.safeParse(raw);
      if (!parsed.success) return { state: "INVALID_REQUEST" };
      const command = parsed.data,
        token = generation,
        scope = await open(token);
      if (!scope) return { state: "DEVICE_NOT_READY" };
      try {
        const supported = await support(scope, token);
        if (command.action === "LIST") {
          const values = await plans(scope, token);
          if (!current(scope, token)) return { state: "SESSION_CHANGED" };
          for (const [key, local] of attached)
            if (!current(scope, token, local)) {
              await stopExact(local);
              attached.delete(key);
            }
          return {
            state: "LIST",
            supported,
            plans: values.map((p) => published(p, attached.get(p.plan_id))),
            serverTime: null,
          };
        }
        if (command.action === "ATTACH") {
          if (!supported) return { state: "UNAVAILABLE" };
          const plan = (await plans(scope, token)).find(
            (p) => p.plan_id === command.planId,
          );
          if (!current(scope, token)) return { state: "SESSION_CHANGED" };
          if (!plan) return { state: "NOT_FOUND" };
          if (plan.revision !== command.expectedRevision)
            return { state: "CONFLICT" };
          const local = await attach(scope, token, plan, command.targets);
          return local
            ? { state: "ATTACHED", plan: published(plan, local) }
            : { state: current(scope, token) ? "CONFLICT" : "SESSION_CHANGED" };
        }
        const original =
          command.action === "RECEIPT" ? command.command : command;
        if (command.action === "RECEIPT") {
          const response = await scope.transport.requestExecution({
            operation: "monitor.receipt",
            payload: { request_id: original.requestId },
          });
          if (!current(scope, token)) return { state: "SESSION_CHANGED" };
          if (!response.ok)
            return {
              state:
                response.status === 404 ? "NOT_FOUND" : "SERVICE_UNAVAILABLE",
            };
          let receipt;
          try {
            receipt = receiptSchema.parse(response.data);
          } catch {
            return { state: "SERVICE_UNAVAILABLE" };
          }
          if (!validReceipt(original, receipt)) return { state: "CONFLICT" };
          return {
            state: "RECORDED",
            requestId: original.requestId,
            plan: published(receipt.plan),
          };
        }
        if (command.action === "CREATE") {
          if (!supported) return { state: "UNAVAILABLE" };
          if (
            !(await options.foreground.validateMonitorBinding(
              command.profileVersionId,
              command.strategyVersionId,
              command.targets,
            )) ||
            !current(scope, token)
          )
            return {
              state: current(scope, token) ? "CONFLICT" : "SESSION_CHANGED",
            };
          const response = await scope.transport.requestExecution({
            operation: "monitor.create",
            payload: {
              schema_version: "monitor-plans-v1",
              request_id: command.requestId,
              profile_version_id: command.profileVersionId,
              strategy_version_id: command.strategyVersionId,
              human_confirmed: true,
            },
          });
          if (!current(scope, token)) return { state: "SESSION_CHANGED" };
          if (!response.ok)
            return response.status === 0 || response.status >= 500
              ? { state: "UNKNOWN", requestId: command.requestId }
              : { state: "CONFLICT" };
          let receipt;
          try {
            receipt = receiptSchema.parse(response.data);
          } catch {
            return { state: "UNKNOWN", requestId: command.requestId };
          }
          if (!validReceipt(command, receipt))
            return { state: "UNKNOWN", requestId: command.requestId };
          const local = await attach(
            scope,
            token,
            receipt.plan,
            command.targets,
          );
          if (!current(scope, token)) return { state: "SESSION_CHANGED" };
          return {
            state: "RECORDED",
            requestId: command.requestId,
            plan: published(receipt.plan, local ?? undefined),
          };
        }
        if (command.state === "ACTIVE" && !supported)
          return { state: "UNAVAILABLE" };
        if (command.state === "ACTIVE" && !command.targets)
          return { state: "INVALID_REQUEST" };
        const prior = attached.get(command.planId);
        if (command.state === "PAUSED" && prior?.running && !prior.taskId)
          return { state: "BUSY" };
        if (command.state === "PAUSED" && prior) {
          prior.stopping = true;
          try {
            await stopExact(prior);
          } catch {
            prior.stopping = false;
            prior.running = false;
            prior.stopUnconfirmed = true;
            prior.lastError = "SOURCE_STOP_FAILED";
            return { state: "SERVICE_UNAVAILABLE" };
          }
          if (!current(scope, token)) return { state: "SESSION_CHANGED" };
          attached.delete(command.planId);
        }
        if (command.state === "ACTIVE") {
          const latest = (await plans(scope, token)).find(
            (plan) => plan.plan_id === command.planId,
          );
          if (!current(scope, token)) return { state: "SESSION_CHANGED" };
          if (!latest || latest.revision !== command.expectedRevision)
            return { state: "CONFLICT" };
          if (
            !(await options.foreground.validateMonitorBinding(
              latest.profile_version_id,
              latest.strategy_version_id,
              command.targets!,
            )) ||
            !current(scope, token)
          )
            return {
              state: current(scope, token) ? "CONFLICT" : "SESSION_CHANGED",
            };
        }
        const response = await scope.transport.requestExecution({
          operation: "monitor.state",
          payload: {
            schema_version: "monitor-plans-v1",
            request_id: command.requestId,
            plan_id: command.planId,
            expected_revision: command.expectedRevision,
            state: command.state,
            human_confirmed: true,
          },
        });
        if (!current(scope, token)) return { state: "SESSION_CHANGED" };
        if (!response.ok)
          return response.status === 0 || response.status >= 500
            ? { state: "UNKNOWN", requestId: command.requestId }
            : { state: "CONFLICT" };
        let receipt;
        try {
          receipt = receiptSchema.parse(response.data);
        } catch {
          return { state: "UNKNOWN", requestId: command.requestId };
        }
        if (!validReceipt(command, receipt))
          return { state: "UNKNOWN", requestId: command.requestId };
        let local: Attachment | undefined;
        if (command.state === "ACTIVE")
          local =
            (await attach(scope, token, receipt.plan, command.targets!)) ??
            undefined;
        return {
          state: "RECORDED",
          requestId: command.requestId,
          plan: published(receipt.plan, local),
        };
      } catch {
        return current(scope, token)
          ? { state: "SERVICE_UNAVAILABLE" }
          : { state: "SESSION_CHANGED" };
      } finally {
        scope.close();
      }
    },
    async tick() {
      if (ticking || closed) return;
      const token = generation;
      ticking = true;
      try {
        const values = [...attached.values()];
        if (values.length) {
          const start = fairCursor % values.length;
          const ordered = [...values.slice(start), ...values.slice(0, start)];
          for (const local of ordered) {
            if (closed || token !== generation) break;
            const scope = await open(token);
            if (!scope) {
              if (!closed) {
                await stopExact(local);
                attached.delete(local.planId);
              }
              continue;
            }
            try {
              if (!current(scope, token, local)) {
                await stopExact(local);
                attached.delete(local.planId);
                continue;
              }
              const plan = (await plans(scope, token)).find(
                (p) => p.plan_id === local.planId,
              );
              if (!current(scope, token, local)) {
                await stopExact(local);
                attached.delete(local.planId);
                continue;
              }
              if (
                !plan ||
                plan.state !== "ACTIVE" ||
                plan.revision !== local.revision ||
                plan.profile_version_id !== local.profileId ||
                plan.strategy_version_id !== local.strategyId ||
                plan.configuration_sha256 !== local.configurationSha256
              ) {
                await stopExact(local);
                attached.delete(local.planId);
                continue;
              }
              const canStart = options.foreground.canStart();
              const response = await scope.transport.requestExecution({
                operation: "monitor.pulse",
                payload: {
                  schema_version: "monitor-runtime-v1",
                  plan_id: local.planId,
                  device_id: local.deviceId,
                  monitor_session_id: local.monitorSessionId,
                  credential_version: local.credentialVersion,
                  targets: local.targets,
                  can_start: canStart,
                },
              });
              if (!current(scope, token, local)) continue;
              if (!response.ok) {
                local.lastError = "SERVICE_UNAVAILABLE";
                continue;
              }
              const pulse = pulseSchema.parse(response.data);
              if (
                pulse.plan_id !== local.planId ||
                pulse.plan_revision !== local.revision
              )
                throw new Error();
              const occurrence = pulse.occurrence;
              if (
                [
                  "WAITING",
                  "SKIPPED_OFFLINE",
                  "SKIPPED_MISSED",
                  "SKIPPED_BUSY",
                ].includes(pulse.state) &&
                occurrence !== null
              )
                throw new Error();
              if (
                ["READY", "RUNNING", "RECOVERY_REQUIRED"].includes(
                  pulse.state,
                ) &&
                !occurrence
              )
                throw new Error();
              if (
                pulse.state === "READY" &&
                (occurrence!.task_id !== null ||
                  occurrence!.start_request.operation !== "START")
              )
                throw new Error();
              if (pulse.state === "RUNNING" && occurrence!.task_id === null)
                throw new Error();
              if (
                occurrence &&
                (!same(occurrence.start_request.targets, local.targets) ||
                  occurrence.start_request.profile_version_id !==
                    local.profileId ||
                  occurrence.start_request.strategy_version_id !==
                    local.strategyId ||
                  occurrence.start_request.configuration_sha256 !==
                    local.configurationSha256 ||
                  occurrence.start_request.device_id !== local.deviceId ||
                  occurrence.start_request.credential_version !==
                    local.credentialVersion)
              )
                throw new Error();
              local.taskId =
                pulse.state === "READY"
                  ? null
                  : (occurrence?.task_id ?? local.taskId);
              local.running = pulse.state === "RUNNING";
              local.lastError =
                pulse.state.startsWith("SKIPPED_") ||
                pulse.state === "RECOVERY_REQUIRED"
                  ? pulse.state
                  : null;
              if (pulse.state === "RECOVERY_REQUIRED") {
                try {
                  await stopExact(local);
                } catch {
                  local.stopUnconfirmed = true;
                  local.lastError = "SOURCE_STOP_FAILED";
                }
                local.running = false;
                continue;
              }
              if (pulse.state === "READY" && canStart) {
                local.running = true;
                const result = await options.foreground.startMonitor(
                  occurrence!.start_request,
                );
                fairCursor = (values.indexOf(local) + 1) % values.length;
                let startedTaskId: string | null = null;
                if (
                  result &&
                  typeof result === "object" &&
                  "state" in result &&
                  String(result.state) === "RECORDED" &&
                  "receipt" in result
                ) {
                  try {
                    const receipt = parseExecutionReceipt(
                      result.receipt,
                      occurrence!.start_request,
                    );
                    if (receipt.operation !== "START") throw new Error();
                    startedTaskId = receipt.task_id;
                    local.taskId = startedTaskId;
                  } catch {
                    local.lastError = "MONITOR_START_FAILED";
                    local.running = false;
                  }
                }
                if (!current(scope, token, local)) {
                  if (startedTaskId) {
                    try {
                      await stopExact(local);
                    } catch {
                      local.stopUnconfirmed = true;
                      local.lastError = "SOURCE_STOP_FAILED";
                    }
                  }
                  continue;
                }
                if (
                  !result ||
                  typeof result !== "object" ||
                  !("state" in result)
                ) {
                  local.lastError = "MONITOR_START_FAILED";
                  local.running = false;
                } else if (String(result.state) === "UNKNOWN") {
                  local.lastError = "MONITOR_START_UNKNOWN";
                  local.running = false;
                } else if (
                  String(result.state) === "RECORDED" &&
                  "receipt" in result
                ) {
                  if (!startedTaskId) local.running = false;
                } else if (String(result.state) !== "RECORDED") {
                  local.lastError = "MONITOR_START_FAILED";
                  local.running = false;
                }
              }
            } catch {
              if (current(scope, token, local))
                local.lastError = "MONITOR_PULSE_FAILED";
            } finally {
              scope.close();
            }
          }
        }
      } finally {
        ticking = false;
      }
    },
    async shutdown() {
      if (closed) return;
      closed = true;
      generation++;
      if (timer) clearInterval(timer);
      const values = [...attached.values()];
      attached.clear();
      await Promise.allSettled(values.map(stopExact));
    },
  };
  if (options.autoStart !== false)
    timer = setInterval(() => {
      void controller.tick();
    }, options.intervalMs ?? 20_000);
  return controller;
}
