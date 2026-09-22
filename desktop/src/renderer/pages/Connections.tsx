import { useEffect, useRef, useState } from "react";
import { ArrowSquareOut, CheckCircle, Plus } from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { DeviceConnectionPreparationNotice, useDeviceConnectionPreparation } from '../app/DeviceConnectionPreparation';
import { PlatformIcon, PlatformLabel } from "../components/Platform";
import { useResource } from "../app/hooks";
import { useConnectionDisconnect } from "./connections/useConnectionDisconnect";
import { DisconnectPanel } from "./connections/DisconnectPanel";
import {
  boundedRequest,
  RequestCancelled,
  RequestTimeout,
} from "../app/boundedRequest";
import {
  Button,
  Field,
  Modal,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
} from "../components/ui";
import {
  PLATFORMS,
  type PlatformConnection,
  type PlatformId,
} from "../domain/models";
import { safeReturnTo } from "../domain/routes";
import { errorMessage, ServiceError } from "../services/contracts";
import { mergeConnectionRead } from "../services/connectionRegistry";
import { ConnectionRegistryTable } from "./connections/ConnectionRegistryTable";
import { PortableRuntimeNotice } from "./connections/PortableRuntimeNotice";

type ConnectingState =
  | "idle"
  | "opening"
  | "waiting"
  | "observation-ended"
  | "checking"
  | "connected"
  | "timeout"
  | "error";
export function ConnectionsPage() {
  const { service, session, route, navigate, notify } = useApp();
  const preparation = useDeviceConnectionPreparation();
  const deviceBlocked = preparation !== null && !preparation.ready;
  const connections = useResource(
    (signal) =>
      boundedRequest(() => service.connections(), {
        signal,
        timeoutMessage: "连接列表读取超时，请重试。",
      }),
    [service, session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version],
  );
  const disconnect = useConnectionDisconnect((connection) => {
    connections.setData((old) => mergeConnectionRead(old, connection));
  });
  const selected = PLATFORMS.find(
    (p) => p.id === route.query.get("connect") && p.id !== "web",
  );
  const modalOpen = route.query.has("connect");
  const returnTo = safeReturnTo(route.query.get("returnTo"));
  const caller = safeReturnTo(route.query.get("returnTo"), "");
  const [platformChoice, setPlatformChoice] = useState<PlatformId>("xhs");
  const [state, setState] = useState<ConnectingState>("idle");
  const [error, setError] = useState("");
  const [opened, setOpened] = useState(false);
  const [loginReady, setLoginReady] = useState(false);
  const [recoverable, setRecoverable] = useState(false);
  const [result, setResult] = useState<PlatformConnection | null>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    generation.current++;
    controller.current?.abort();
    setState("idle");
    setError("");
    setOpened(false);
    setLoginReady(false);
    setRecoverable(false);
    setResult(null);
    return () => {
      generation.current++;
      controller.current?.abort();
      if (selected && modalOpen) void service.cancelConnection?.(selected.id).catch(() => {});
    };
  }, [selected?.id, modalOpen, service, session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version]);
  useEffect(() => {
    if (state !== "waiting") return;
    const timer = window.setTimeout(() => {
      generation.current++;
      setState("observation-ended");
    }, 120_000);
    return () => window.clearTimeout(timer);
  }, [state]);
  useEffect(() => {
    if (state !== 'waiting' || !selected || !service.connectionLoginStatus) return;
    const request = generation.current;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = () => !abort.signal.aborted && generation.current === request;
    const poll = async () => {
      if (!current()) return;
      try {
        const status = await boundedRequest(() => service.connectionLoginStatus!(selected.id), {
          signal: abort.signal, timeoutMs: 5000,
          timeoutMessage: '登录状态读取超时，请核对原生窗口后重新打开。',
        });
        if (!current()) return;
        setLoginReady(status === 'LOGIN_READY');
        timer = setTimeout(() => void poll(), 1000);
      } catch (e) {
        if (!current() || e instanceof RequestCancelled) return;
        setOpened(false);
        setLoginReady(false);
        setRecoverable(e instanceof ServiceError && e.code === 'LOGIN_EXPIRED');
        setState(e instanceof RequestTimeout ? 'timeout' : 'error');
        setError(errorMessage(e));
      }
    };
    void poll();
    return () => {abort.abort(); if (timer !== undefined) clearTimeout(timer);};
  }, [state, selected?.id, service, session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version]);
  const busy = state === "opening" || state === "checking";
  const close = () => {
    generation.current++;
    controller.current?.abort();
    if (selected) void service.cancelConnection?.(selected.id).catch(() => {});
    navigate(returnTo);
  };
  const openPlatform = (id: string) => {
    const params = new URLSearchParams({ connect: id });
    if (returnTo !== "/connections") params.set("returnTo", returnTo);
    navigate("/connections?" + params.toString());
  };
  const openLogin = async () => {
    if (
      !selected ||
      deviceBlocked ||
      busy ||
      disconnect.records.some((record) => record.platform === selected.id)
    )
      return;
    try {
      disconnect.assertConnectable(selected.id);
    } catch (error) {
      setError(errorMessage(error));
      return;
    }
    const request = ++generation.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setState("opening");
    setError("");
    setOpened(false);
    setLoginReady(false);
    setRecoverable(false);
    setResult(null);
    try {
      await boundedRequest((signal) => service.connect(selected.id, signal), {
        signal: abort.signal,
        timeoutMessage:
          "打开登录窗口超时，窗口状态尚未确认。请先核对原生窗口后重试；当前未记为已连接。",
      });
      if (request !== generation.current) return;
      setOpened(true);
      setState("waiting");
    } catch (e) {
      if (request === generation.current && !(e instanceof RequestCancelled)) {
        if (e instanceof ServiceError && (e.code === 'UNKNOWN' || e.code === 'WAITING_LOGIN')) setRecoverable(true);
        setState(e instanceof RequestTimeout ? "timeout" : "error");
        setError(errorMessage(e));
      }
    }
  };
  const check = async () => {
    if (deviceBlocked || !selected || (!opened && !recoverable) || busy) return;
    const request = ++generation.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setState("checking");
    setError("");
    try {
      const connection = await boundedRequest(
        () => service.checkConnection(selected.id),
        {
          signal: abort.signal,
          timeoutMessage:
            "检查连接超时，连接结果尚未确认。可重新检查，现有任务配置不会改变。",
        },
      );
      if (request !== generation.current) return;
      if (connection.platform !== selected.id) {
        setState("error");
        setError("返回的连接与当前平台不一致，请重新检查。");
        return;
      }
      setResult(connection);
      connections.setData((old) => mergeConnectionRead(old, connection));
      if (connection.status === "CONNECTED") {
        setState("connected");
      } else {
        setState("error");
        setError(
          connection.reason || "登录尚未完成，请在平台原生页面处理后重新检查。",
        );
      }
    } catch (e) {
      if (request === generation.current && !(e instanceof RequestCancelled)) {
        setState(e instanceof RequestTimeout ? "timeout" : "error");
        if (e instanceof ServiceError && ['LOGIN_EXPIRED','PLATFORM_AUTH_REQUIRED','PLATFORM_VERIFICATION_REQUIRED','ACCOUNT_MISMATCH'].includes(e.code)) {
          setOpened(false);
          setLoginReady(false);
          setRecoverable(e.code === 'LOGIN_EXPIRED');
        }
        setError(errorMessage(e));
      }
    }
  };
  const currentState =
    state === "opening"
      ? "正在打开登录窗口"
      : state === "checking"
        ? "正在检查连接"
        : state === "connected"
          ? "账号已连接"
          : state === "observation-ended"
            ? loginReady ? "登录已识别，待检查连接" : "等待登录已结束"
          : state === "timeout"
            ? "等待超时"
            : state === "error"
              ? "连接未完成"
              : opened
                ? loginReady ? "登录已完成，待检查连接" : "等待登录"
                : "等待打开登录窗口";
  return (
    <>
      <PageHeader title="账号与授权" />
      <PortableRuntimeNotice />
      <div className="section-heading">
        <Tabs
          items={[
            { key: "connections", label: "平台连接" },
            { key: "settings", label: "设备与使用授权" },
          ]}
          active="connections"
          onChange={(key) => {
            if (key === "settings")
              navigate(
                caller ? `/settings?returnTo=${encodeURIComponent(caller)}` : "/settings",
              );
          }}
        />
        <Button variant="primary" onClick={() => openPlatform("select")}>
          <Plus />
          添加平台连接
        </Button>
      </div>
      <p className="page-description">
        管理已连接的平台账号。
      </p>
      <ResourceStatus
        loading={connections.loading}
        error={connections.error}
        onRetry={() => void connections.reload()}
      />
      {disconnect.records.map((record) => (
        <Notice
          key={record.key}
          tone="warning"
          action={
            <Button onClick={() => disconnect.openRecord(record)}>
              核对断开结果（
              {PLATFORMS.find((item) => item.id === record.platform)?.name}）
            </Button>
          }
        >
          <PlatformLabel platform={record.platform} />{" "}
          的原账号断开结果待核对，暂不重复断开或重新连接。
        </Notice>
      ))}
      {!disconnect.target && disconnect.message && (
        <Notice tone="warning">{disconnect.message}</Notice>
      )}
      <ConnectionRegistryTable
        key={JSON.stringify([session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version])}
        rows={connections.data}
        loading={connections.loading}
        error={connections.error}
        pendingPlatforms={disconnect.records.map(record => record.platform)}
        onOpen={openPlatform}
        onDisconnect={disconnect.open}
        onRefresh={() => void connections.reload()}
      />
      <section className="connection-notes">
        <h3>说明</h3>
        <ul>
          <li>连接状态和能力以平台实际检查结果为准。</li>
          <li>断开连接前，请确认对应任务的影响；额外验证在平台页面中完成。</li>
        </ul>
      </section>
      {modalOpen && !selected && (
        <Modal
          title="添加平台连接"
          onClose={close}
          footer={
            <>
              <Button onClick={close}>取消</Button>
              <Button
                variant="primary"
                onClick={() => openPlatform(platformChoice)}
              >
                下一步
              </Button>
            </>
          }
        >
          <Field label="选择平台" required>
            <div className="platform-choice-control">
              <PlatformIcon platform={platformChoice} size={24} />
              <select
                aria-label="选择连接平台"
                value={platformChoice}
                onChange={(e) =>
                  setPlatformChoice(e.target.value as PlatformId)
                }
              >
                {PLATFORMS.filter((p) => p.id !== "web").map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          </Field>
          <p className="field-hint">下一步将在平台原生页面登录账号。</p>
        </Modal>
      )}
      {modalOpen && selected && (
        <Modal
          title={`连接${selected.name}`}
          onClose={close}
          footer={
            state === "connected" ? (
              <>
                <Button onClick={close}>关闭</Button>
                <Button
                  variant="primary"
                  onClick={() => {
                    notify(`${selected.name}已完成连接检查。`, "success");
                    close();
                  }}
                >
                  完成并返回
                </Button>
              </>
            ) : (
              <>
                <Button onClick={close}>取消</Button>
                <Button
                  disabled={deviceBlocked || (!opened && !recoverable) || busy}
                  loading={state === "checking"}
                  onClick={() => void check()}
                >
                  我已完成登录，检查连接
                </Button>
                <Button
                  variant="primary"
                  loading={state === "opening"}
                  disabled={
                    deviceBlocked ||
                    state === "checking" ||
                    disconnect.records.some(
                      (record) => record.platform === selected.id,
                    )
                  }
                  onClick={() => void openLogin()}
                >
                  <ArrowSquareOut />
                  打开登录窗口
                </Button>
              </>
            )
          }
        >
          {state !== "connected" && <>
          <ol className="connection-steps" aria-label="连接步骤">
            <li className="done">
              <CheckCircle aria-hidden />
              选择平台
            </li>
            <li className="active">
              <span>2</span>登录账号
            </li>
            <li>
              <span>3</span>检查连接
            </li>
          </ol>
          <h3>本机浏览器登录</h3>
          <p className="muted">
            账号登录在平台原生页面完成，意客AI不要求输入平台密码。
          </p>
          </>}
          {deviceBlocked ? <DeviceConnectionPreparationNotice /> : <div className="connection-status">
            <PlatformIcon platform={selected.id} size={32} />
            <div>
              <span className="muted">当前状态</span>
              <h3 role="status">{currentState}</h3>
              {state === "connected" ? (
                <>
                  {result?.accountName?.trim() ? <p>{result.accountName.trim()}</p> : null}
                  {result && result.capabilities.length === 0 && (
                    <Notice tone="warning">
                      账号连接成功，但尚无已验证的采集或触达能力；任务启动条件仍需检查。
                    </Notice>
                  )}
                </>
              ) : <p>
                {opened
                    ? loginReady ? '请本人点击“我已完成登录，检查连接”，完成当前账号连接核验。' : `在本机浏览器中完成${selected.name}账号登录。`
                    : recoverable ? '点击“检查连接”核对当前状态，无需重复打开登录窗口。' : "点击下方按钮打开平台登录窗口。"}
              </p>}
            </div>
          </div>}
          {state === "observation-ended" && <Notice tone="warning">
            自动观察已结束，尚未确认连接。请点击“我已完成登录，检查连接”核对当前状态；若检查提示未登录，再重新打开登录窗口。
          </Notice>}
          {error && <Notice tone="error">{error}</Notice>}
          {state !== "connected" && <p className="field-hint">
            扫码、验证码和额外验证均在平台原生页面处理。
          </p>}
        </Modal>
      )}
      <DisconnectPanel action={disconnect} rows={connections.data} />
    </>
  );
}
