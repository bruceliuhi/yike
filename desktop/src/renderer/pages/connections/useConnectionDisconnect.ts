import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest, RequestCancelled } from "../../app/boundedRequest";
import { useOperationLedger } from "../../app/operationLedger";
import {
  checkedDisconnectConnection,
  disconnectKey,
  disconnectRecords,
  disconnectTarget,
  type DisconnectRecord,
  type DisconnectTarget,
} from "../../domain/connectionDisconnect";
import type { PlatformConnection } from "../../domain/models";
import { errorMessage } from "../../services/contracts";

type Phase = "idle" | "preflight" | "submitting" | "checking";
interface View {
  identity: object;
  target: DisconnectTarget | null;
  phase: Phase;
  message: string;
}

export function useConnectionDisconnect(
  onConnection: (connection: PlatformConnection) => void,
) {
  const { service, session, route, notify } = useApp();
  const [entries, setEntries] = useOperationLedger(
    "connection-disconnects",
    session.userId,
  );
  const identity = useMemo(
    () => ({}),
    [service, session.userId, session.authenticated],
  );
  const currentIdentity = useRef(identity);
  currentIdentity.current = identity;
  const mounted = useRef(true);
  const request = useRef(0);
  const active = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const [view, setView] = useState<View>({
    identity,
    target: null,
    phase: "idle",
    message: "",
  });
  const current = () => mounted.current && currentIdentity.current === identity;
  const visible =
    view.identity === identity
      ? view
      : { identity, target: null, phase: "idle" as const, message: "" };
  const records = session.authenticated ? disconnectRecords(entries) : [];
  const update = (patch: Partial<Omit<View, "identity">>) => {
    if (current())
      setView((old) => ({
        ...(old.identity === identity
          ? old
          : { target: null, phase: "idle", message: "" }),
        identity,
        ...patch,
      }));
  };
  const cancelWait = () => {
    request.current++;
    active.current?.abort();
    busy.current = false;
  };
  const close = () => {
    cancelWait();
    update({ target: null, phase: "idle", message: "" });
  };
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancelWait();
    };
  }, []);
  useEffect(() => {
    cancelWait();
    update({ target: null, phase: "idle", message: "" });
  }, [identity, route.path, route.query.get("connect")]);

  const read = async (target: DisconnectTarget, signal: AbortSignal) => {
    const [who, raw] = await boundedRequest(
      () =>
        Promise.all([
          service.session(),
          service.checkConnection(target.platform),
        ]),
      {
        signal,
        timeoutMessage: "连接状态核对超时，原请求记录已保留，可稍后重新核对。",
      },
    );
    if (
      !current() ||
      signal.aborted ||
      !who.authenticated ||
      !who.userId ||
      who.userId !== session.userId
    )
      throw new Error("客户身份已变化或失效，未继续操作原账号。");
    return checkedDisconnectConnection(raw, target);
  };
  const inspect = async (record: DisconnectRecord, signal: AbortSignal) => {
    const connection = await read(record, signal);
    if (!current() || signal.aborted) return;
    onConnection(connection);
    let settled = false;
    if (
      connection.status === "DISCONNECTED" &&
      (!connection.accountId || connection.accountId === record.accountId)
    ) {
      setEntries((old) => {
        if (old[record.key] !== "ACKNOWLEDGED") return old;
        const next = { ...old };
        delete next[record.key];
        settled = true;
        return next;
      });
      if (settled) {
        update({ target: null, phase: "idle", message: "" });
        notify("原账号已断开，并已核对当前连接状态。", "success");
        return;
      }
      update({
        message:
          "当前平台显示未连接，但原断开请求回执尚未收到。记录继续保留，不重复断开或重新连接。",
      });
    } else if (
      connection.accountId &&
      connection.accountId !== record.accountId
    ) {
      update({
        message:
          "当前平台返回了其他账号，无法据此确认原账号的断开结果。未对其他账号执行操作，原记录继续保留。",
      });
    } else {
      update({
        message:
          "原账号尚未确认断开。连接失效、受限或仍连接都不是确定断开，当前不会重复提交。",
      });
    }
  };
  const run = async (
    phase: Phase,
    action: (signal: AbortSignal) => Promise<void>,
  ) => {
    if (busy.current || !current() || !session.authenticated || !session.userId)
      return;
    busy.current = true;
    const id = ++request.current;
    const abort = new AbortController();
    active.current = abort;
    update({ phase, message: "" });
    try {
      await action(abort.signal);
    } catch (error) {
      if (
        current() &&
        id === request.current &&
        !(error instanceof RequestCancelled)
      )
        update({ message: errorMessage(error) });
    } finally {
      if (id === request.current) {
        busy.current = false;
        update({ phase: "idle" });
      }
    }
  };
  const open = (connection: PlatformConnection) => {
    if (!current() || !session.authenticated || busy.current) return;
    try {
      const pending = records.find(
        (record) => record.platform === connection.platform,
      );
      const target = pending || disconnectTarget(connection);
      update({ target, phase: "idle", message: "" });
    } catch (error) {
      update({ message: errorMessage(error) });
    }
  };
  const openRecord = (record: DisconnectRecord) => {
    if (!current() || !session.authenticated || busy.current) return;
    update({ target: record, phase: "idle", message: "" });
  };
  const start = () => {
    const target = visible.target;
    if (!target) return;
    void run("preflight", async (signal) => {
      const connection = await read(target, signal);
      if (!current() || signal.aborted) return;
      if (
        connection.accountId !== target.accountId ||
        connection.status !== "CONNECTED"
      ) {
        onConnection(connection);
        throw new Error(
          "账号或连接状态已变化，本次未发送断开请求。请重新选择并确认。",
        );
      }
      const key = disconnectKey(target, crypto.randomUUID());
      setEntries((old) => {
        if (
          disconnectRecords(old).some(
            (record) => record.platform === target.platform,
          )
        )
          throw new Error("该平台已有断开请求待核对，未重复提交。");
        return { ...old, [key]: "PENDING" };
      });
      update({ phase: "submitting" });
      // Capture the original user's ledger setter. Late ACKs may update only
      // that durable record, never a new identity's UI or current connection.
      const operation = service.disconnect(target.platform).then((value) => {
        if (value !== undefined)
          throw new Error("断开响应格式不明确，原请求仍待核对。");
        setEntries((old) =>
          old[key] === "PENDING" ? { ...old, [key]: "ACKNOWLEDGED" } : old,
        );
      });
      await boundedRequest(() => operation, {
        signal,
        timeoutMessage:
          "断开请求等待超时，结果尚未确认。记录已保留，请核对原账号状态；不会重复断开。",
      });
      if (!current() || signal.aborted) return;
      update({ phase: "checking" });
      await inspect(
        { key, ...target, requestId: JSON.parse(key)[2], acknowledged: true },
        signal,
      );
    });
  };
  const pending =
    visible.target &&
    records.find((record) => record.platform === visible.target!.platform);
  const check = () => {
    if (pending) void run("checking", (signal) => inspect(pending, signal));
  };
  const assertConnectable = (platform: string) => {
    if (!current() || !session.authenticated || !session.userId)
      throw new Error("请先登录客户空间，再连接平台账号。");
    setEntries((old) => {
      if (disconnectRecords(old).some((record) => record.platform === platform))
        throw new Error("该平台的原断开请求仍待核对，当前不能重新连接。");
      return old;
    });
  };
  return {
    ...visible,
    records,
    pending,
    open,
    openRecord,
    close,
    start,
    check,
    assertConnectable,
    busy: visible.phase !== "idle",
  };
}
