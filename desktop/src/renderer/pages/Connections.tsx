import { useEffect, useRef, useState } from "react";
import { ArrowSquareOut, CheckCircle, Plus } from "@phosphor-icons/react";
import { useApp } from "../app/context";
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
  Badge,
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
import { errorMessage } from "../services/contracts";

type ConnectingState =
  | "idle"
  | "opening"
  | "waiting"
  | "checking"
  | "connected"
  | "timeout"
  | "error";
const connectionLabel: Record<PlatformConnection["status"], string> = {
  CONNECTED: "已连接",
  DISCONNECTED: "未连接",
  EXPIRED: "登录已失效",
  LIMITED: "连接受限",
  UNAVAILABLE: "连接服务待接通",
};

export function ConnectionsPage() {
  const { service, session, route, navigate, notify } = useApp();
  const connections = useResource(
    () =>
      boundedRequest(() => service.connections(), {
        timeoutMessage: "连接列表读取超时，请重试。",
      }),
    [service, session.userId],
  );
  const disconnect = useConnectionDisconnect((connection) => {
    connections.setData((old) => [
      ...(old || []).filter((item) => item.platform !== connection.platform),
      connection,
    ]);
  });
  const selected = PLATFORMS.find(
    (p) => p.id === route.query.get("connect") && p.id !== "web",
  );
  const modalOpen = route.query.has("connect");
  const returnTo = safeReturnTo(route.query.get("returnTo"));
  const [platformChoice, setPlatformChoice] = useState<PlatformId>("xhs");
  const [state, setState] = useState<ConnectingState>("idle");
  const [error, setError] = useState("");
  const [opened, setOpened] = useState(false);
  const [result, setResult] = useState<PlatformConnection | null>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    generation.current++;
    controller.current?.abort();
    setState("idle");
    setError("");
    setOpened(false);
    setResult(null);
    return () => {
      generation.current++;
      controller.current?.abort();
    };
  }, [selected?.id, modalOpen, session.userId]);
  useEffect(() => {
    if (state !== "waiting") return;
    const timer = window.setTimeout(() => {
      generation.current++;
      setState("timeout");
      setError("等待登录已超时。可重新打开登录窗口，或再次检查连接。");
    }, 120_000);
    return () => window.clearTimeout(timer);
  }, [state]);
  const busy = state === "opening" || state === "checking";
  const close = () => {
    generation.current++;
    controller.current?.abort();
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
    setResult(null);
    try {
      await boundedRequest(() => service.connect(selected.id), {
        signal: abort.signal,
        timeoutMessage:
          "打开登录窗口超时，窗口状态尚未确认。请先核对原生窗口后重试；当前未记为已连接。",
      });
      if (request !== generation.current) return;
      setOpened(true);
      setState("waiting");
    } catch (e) {
      if (request === generation.current && !(e instanceof RequestCancelled)) {
        setState(e instanceof RequestTimeout ? "timeout" : "error");
        setError(errorMessage(e));
      }
    }
  };
  const check = async () => {
    if (!selected || !opened || busy) return;
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
      connections.setData((old) => [
        ...(old || []).filter((c) => c.platform !== connection.platform),
        connection,
      ]);
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
          : state === "timeout"
            ? "等待超时"
            : state === "error"
              ? "连接未完成"
              : opened
                ? "等待登录"
                : "等待打开登录窗口";
  return (
    <>
      <PageHeader title="账号与授权" />
      <div className="section-heading">
        <Tabs
          items={[
            { key: "connections", label: "平台连接" },
            { key: "settings", label: "设备与使用授权" },
          ]}
          active="connections"
          onChange={(key) => {
            if (key === "settings") navigate("/settings");
          }}
        />
        <Button variant="primary" onClick={() => openPlatform("select")}>
          <Plus />
          添加平台连接
        </Button>
      </div>
      <p className="page-description">
        连接用于采集或触达，能力按平台分别显示。
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
      <div className="table-scroll">
        <table className="connection-table">
          <thead>
            <tr>
              <th>平台</th>
              <th>当前账号</th>
              <th>连接状态</th>
              <th>可用能力</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {PLATFORMS.map((platform) => {
              const connection = connections.data?.find(
                (c) => c.platform === platform.id,
              );
              const isWeb = platform.id === "web";
              return (
                <tr key={platform.id}>
                  <td>
                    <PlatformLabel platform={platform.id} size={22} />
                  </td>
                  <td>
                    {isWeb
                      ? "无需账号"
                      : connection?.accountName || connection?.accountId || "—"}
                  </td>
                  <td>
                    {isWeb ? (
                      "—"
                    ) : (
                      <Badge
                        tone={
                          connection?.status === "CONNECTED"
                            ? "green"
                            : connection?.status === "EXPIRED" ||
                                connection?.status === "LIMITED"
                              ? "orange"
                              : "neutral"
                        }
                      >
                        {connection
                          ? connectionLabel[connection.status]
                          : "待读取连接状态"}
                      </Badge>
                    )}
                  </td>
                  <td>
                    {connection?.capabilities.length
                      ? connection.capabilities.join("、")
                      : isWeb
                        ? "公开页面读取（范围待验收）"
                        : "待检查平台能力"}
                  </td>
                  <td>
                    {!isWeb && (
                      <div className="inline-actions">
                        <Button
                          disabled={disconnect.records.some(
                            (record) => record.platform === platform.id,
                          )}
                          onClick={() => openPlatform(platform.id)}
                        >
                          {connection?.status === "CONNECTED"
                            ? "查看连接"
                            : connection?.status === "EXPIRED"
                              ? "重新连接"
                              : "连接"}
                        </Button>
                        {connection?.status === "CONNECTED" && (
                          <Button
                            variant="ghost"
                            disabled={disconnect.records.some(
                              (record) => record.platform === platform.id,
                            )}
                            onClick={() => disconnect.open(connection)}
                          >
                            断开
                          </Button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
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
                  disabled={!opened || busy}
                  loading={state === "checking"}
                  onClick={() => void check()}
                >
                  我已完成登录，检查连接
                </Button>
                <Button
                  variant="primary"
                  loading={state === "opening"}
                  disabled={
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
          <ol className="connection-steps" aria-label="连接步骤">
            <li className="done">
              <CheckCircle aria-hidden />
              选择平台
            </li>
            <li className={state === "connected" ? "done" : "active"}>
              <span>2</span>登录账号
            </li>
            <li className={state === "connected" ? "active" : ""}>
              <span>3</span>检查连接
            </li>
          </ol>
          <h3>本机浏览器登录</h3>
          <p className="muted">
            账号登录在平台原生页面完成，意客AI不要求输入平台密码。
          </p>
          <div className="connection-status">
            <PlatformIcon platform={selected.id} size={32} />
            <div>
              <span className="muted">当前状态</span>
              <h3 role="status">{currentState}</h3>
              <p>
                {state === "connected"
                  ? `${result?.accountName || result?.accountId || "账号信息待读取"} · ${result?.capabilities.length ? result.capabilities.join("、") : "暂无通过检查的执行能力"}`
                  : opened
                    ? `在本机浏览器中完成${selected.name}账号登录。`
                    : "点击下方按钮打开平台登录窗口。"}
              </p>
            </div>
          </div>
          {error && <Notice tone="error">{error}</Notice>}
          {state === "connected" && !result?.capabilities.length && (
            <Notice tone="warning">
              账号连接成功，但尚无已验证的采集或触达能力；任务启动条件仍需检查。
            </Notice>
          )}
          <p className="field-hint">
            扫码、验证码和额外验证均在平台原生页面处理。
          </p>
        </Modal>
      )}
      <DisconnectPanel action={disconnect} />
    </>
  );
}
