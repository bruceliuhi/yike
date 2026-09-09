import { useState } from "react";
import { useApp } from "../app/context";
import { clearLocalDrafts, useAction, useResource } from "../app/hooks";
import { accountSchema } from "../domain/management";
import { safeReturnTo } from "../domain/routes";
import {
  managementRequest,
  unavailableManagement,
} from "../services/management";
import {
  CustomerDataActions,
  ManagementAction,
  PendingManagement,
  UpdateManagement,
} from "./settings/ManagementActions";
import {
  Badge,
  Button,
  Confirm,
  Field,
  Modal,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
} from "../components/ui";

type SettingsDialog =
  | "bind"
  | "export"
  | "backup"
  | "support"
  | "diagnostic"
  | "update"
  | null;
const dialogTitles: Record<Exclude<SettingsDialog, null>, string> = {
  bind: "绑定本机设备",
  export: "客户数据导出",
  backup: "备份与恢复",
  support: "联系支持",
  diagnostic: "脱敏诊断信息",
  update: "检查更新",
};

export function SettingsPage() {
  const { service, session, route, navigate, notify, refreshSession } = useApp();
  const caller = safeReturnTo(route.query.get("returnTo"), "");
  const info = useResource(() => service.info(), [service]);
  const activation = useAction();
  const logout = useAction();
  const copying = useAction();
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [activationSent, setActivationSent] = useState(false);
  const management = service.management ?? unavailableManagement;
  const account = useResource(
    async () =>
      accountSchema.parse(await managementRequest(() => management.account())),
    [management, session.userId],
  );
  const refreshAccount = () => {
    void account.reload();
  };
  const licenseLabels = {
    UNKNOWN: "待核验",
    INACTIVE: "未激活",
    ACTIVE: "已激活",
    EXPIRED: "已过期",
    SUSPENDED: "已停用",
  };
  const deviceLabels = {
    UNBOUND: "尚未绑定",
    BOUND: "已绑定",
    REVOKED: "已撤销",
    OFFLINE: "已绑定 · 离线",
  };
  const [dialog, setDialog] = useState<SettingsDialog>(null);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const platform = info.data?.platform;
  const platformName = platform
    ? { darwin: "macOS", win32: "Windows", linux: "Linux" }[platform] ||
      platform
    : "—";
  const diagnostic = JSON.stringify(
    {
      product: "意客AI",
      version: info.data?.version || null,
      platform: platform || null,
      serviceConfigured: info.data?.serviceConfigured ?? null,
    },
    null,
    2,
  );
  const activate = async () => {
    if (!code.trim()) {
      setCodeError("请输入授权码。");
      return;
    }
    setCodeError("");
    const done = await activation.run(async () => {
      await service.activate(code.trim());
      return true;
    });
    if (done) {
      setCode("");
      setActivationSent(true);
      refreshAccount();
      notify("激活请求已完成，请以服务端授权结果为准。");
    }
  };
  const logoutNow = async () => {
    await logout.run(async () => {
      let remoteError: unknown;
      try {
        await service.logout();
      } catch (error) {
        remoteError = error;
      }
      const next = await refreshSession();
      if (!next.authenticated) {
        clearLocalDrafts();
        setCode("");
        setLogoutOpen(false);
        if (remoteError)
          notify(
            "已离开客户空间并清除本机草稿，服务端注销结果尚未确认。",
            "info",
          );
        navigate("/login");
        return;
      }
      if (remoteError) throw remoteError;
      throw new Error("当前会话仍有效，尚未退出。请重试。");
    });
  };
  const copyDiagnostic = async () => {
    const done = await copying.run(async () => {
      await service.copy(diagnostic);
      return true;
    });
    if (done) notify("脱敏诊断已复制。", "success");
  };
  return (
    <div className="settings-page">
      <PageHeader title="账号与授权" />
      <Tabs
        items={[
          { key: "connections", label: "平台连接" },
          { key: "settings", label: "设备与使用授权" },
        ]}
        active="settings"
        onChange={(key) => {
          if (key === "connections")
            navigate(
              caller ? `/connections?returnTo=${encodeURIComponent(caller)}` : "/connections",
            );
        }}
      />
      <ResourceStatus
        loading={info.loading}
        error={info.error}
        onRetry={() => void info.reload()}
      />
      <section className="settings-section">
        <h2>使用授权</h2>
        <div className="settings-row">
          <span>授权状态</span>
          <Badge
            tone={
              account.data?.license.status === "ACTIVE" ? "green" : "orange"
            }
          >
            {account.data
              ? licenseLabels[account.data.license.status]
              : activationSent
                ? "等待核验"
                : "待核验"}
          </Badge>
        </div>
        <div className="settings-row">
          <label htmlFor="activation-code">授权码</label>
          <div className="inline-actions">
            <input
              id="activation-code"
              aria-label="授权码"
              type="password"
              autoComplete="off"
              maxLength={128}
              value={code}
              placeholder="请输入授权码"
              onChange={(e) => {
                setCode(e.target.value);
                setCodeError("");
                activation.setError("");
              }}
            />
            <Button
              variant="primary"
              loading={activation.busy}
              onClick={() => void activate()}
            >
              激活
            </Button>
          </div>
        </div>
        {codeError && (
          <p className="field-error" role="alert">
            {codeError}
          </p>
        )}
        {activation.error && <Notice tone="error">{activation.error}</Notice>}
        <div className="settings-row">
          <span>有效期</span>
          <span>
            {account.data?.license.expiresAt
              ? new Date(account.data.license.expiresAt).toLocaleString("zh-CN")
              : "—"}
          </span>
        </div>
        {service.management && (
          <ResourceStatus
            loading={account.loading}
            error={account.error}
            onRetry={() => void account.reload()}
          />
        )}
      </section>
      <section className="settings-section">
        <h2>设备管理</h2>
        <div className="settings-row">
          <span>运行环境</span>
          <span>{platformName}</span>
          <Button onClick={() => setDialog("bind")}>
            {account.data &&
            ["BOUND", "OFFLINE"].includes(account.data.device.status)
              ? "解绑设备"
              : "绑定设备"}
          </Button>
        </div>
        <div className="settings-row">
          <span>设备状态</span>
          <span>
            {account.data
              ? `${account.data.device.name} · ${deviceLabels[account.data.device.status]}`
              : "尚未完成绑定核验"}
          </span>
        </div>
        <div className="settings-row">
          <span>客户服务</span>
          <span>
            {info.data
              ? info.data.serviceConfigured
                ? "已配置服务地址"
                : "尚未配置服务地址"
              : "待检查"}
          </span>
        </div>
      </section>
      <section className="settings-section">
        <h2>版本与数据</h2>
        <div className="settings-row">
          <span>当前版本</span>
          <span>{info.data?.version || "—"}</span>
          <Button onClick={() => setDialog("update")}>检查更新</Button>
        </div>
        <div className="settings-row">
          <span>客户数据</span>
          <span className="muted">按当前客户空间授权范围导出</span>
          <Button onClick={() => setDialog("export")}>导出数据</Button>
        </div>
        <div className="settings-row">
          <span>备份与恢复</span>
          <span className="muted">先检查文件、恢复范围与覆盖影响</span>
          <Button onClick={() => setDialog("backup")}>备份与恢复</Button>
        </div>
        <div className="settings-row">
          <span>本机草稿</span>
          <span className="muted">当前会话的配置与资料草稿</span>
          <Button onClick={() => setClearOpen(true)}>清除本机草稿</Button>
        </div>
      </section>
      <section className="settings-section">
        <h2>支持与诊断</h2>
        <div className="settings-row">
          <span>脱敏诊断</span>
          <span className="muted">版本、运行环境和服务配置状态</span>
          <Button
            onClick={() => {
              copying.setError("");
              setDialog("diagnostic");
            }}
          >
            查看脱敏诊断
          </Button>
        </div>
        <div className="settings-row">
          <span>联系支持</span>
          <span />
          <Button onClick={() => setDialog("support")}>联系支持</Button>
        </div>
        {session.authenticated && (
          <div className="settings-row">
            <span>当前会话</span>
            <span>已登录</span>
            <Button onClick={() => setLogoutOpen(true)}>退出登录</Button>
          </div>
        )}
      </section>
      <PendingManagement account={account.data} changed={refreshAccount} />
      {dialog && (
        <Modal
          title={
            dialog === "bind" &&
            account.data &&
            ["BOUND", "OFFLINE"].includes(account.data.device.status)
              ? "解绑本机设备"
              : dialogTitles[dialog]
          }
          onClose={() => setDialog(null)}
          footer={
            <>
              <Button onClick={() => setDialog(null)}>关闭</Button>
              {dialog === "diagnostic" && (
                <Button
                  variant="primary"
                  loading={copying.busy}
                  onClick={() => void copyDiagnostic()}
                >
                  复制脱敏诊断
                </Button>
              )}
            </>
          }
        >
          {dialog === "bind" && (
            <ManagementAction
              account={account.data}
              kind={
                account.data &&
                ["BOUND", "OFFLINE"].includes(account.data.device.status)
                  ? "unbind-device"
                  : "bind-device"
              }
              changed={refreshAccount}
            />
          )}
          {(dialog === "export" || dialog === "backup") && (
            <CustomerDataActions
              account={account.data}
              backup={dialog === "backup"}
              changed={refreshAccount}
            />
          )}
          {dialog === "support" && (
            <>
              <p>请联系为你开通客户空间的服务方。</p>
              <p>
                可提供本页的脱敏诊断信息；请勿发送登录凭证、授权码或平台会话。
              </p>
              <Button onClick={() => setDialog("diagnostic")}>
                查看脱敏诊断
              </Button>
            </>
          )}
          {dialog === "diagnostic" && (
            <>
              <Field
                label="诊断内容"
                hint="不包含访问凭证、客户记录、平台会话或数据库信息。"
              >
                <textarea
                  aria-label="脱敏诊断内容"
                  rows={8}
                  readOnly
                  value={diagnostic}
                />
              </Field>
              {copying.error && <Notice tone="error">{copying.error}</Notice>}
            </>
          )}
          {dialog === "update" && (
            <UpdateManagement account={account.data} changed={refreshAccount} />
          )}
        </Modal>
      )}
      {clearOpen && (
        <Confirm
          title="清除本机草稿？"
          confirmText="清除草稿"
          danger
          onCancel={() => setClearOpen(false)}
          onConfirm={() => {
            clearLocalDrafts();
            setClearOpen(false);
            notify("当前会话的本机草稿已清除，客户数据库保持不变。");
          }}
        >
          <p>
            将清除本机保存的任务配置、画像编辑和资料草稿。已提交到客户空间的记录不受影响。
          </p>
        </Confirm>
      )}
      {logoutOpen && (
        <Confirm
          title="退出当前客户空间？"
          confirmText="退出登录"
          loading={logout.busy}
          onCancel={() => {
            if (!logout.busy) setLogoutOpen(false);
          }}
          onConfirm={() => void logoutNow()}
        >
          <p>退出后会清除当前会话及本机草稿。尚未提交的内容将无法恢复。</p>
          {logout.error && <Notice tone="error">{logout.error}</Notice>}
        </Confirm>
      )}
    </div>
  );
}
