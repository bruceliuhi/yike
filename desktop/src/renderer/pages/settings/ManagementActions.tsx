import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useAction, useResource } from "../../app/hooks";
import { Button, Field, Notice, ResourceStatus } from "../../components/ui";
import {
  digest,
  inputDigest,
  planSchema,
  readBackup,
  updateSchema,
  type AccountState,
  type ManagementInput,
  type ManagementPlan,
} from "../../domain/management";
import { downloadErrorMessage, downloadText } from "../../services/download";
import {
  managementRequest,
  unavailableManagement,
} from "../../services/management";
import { useManagementScope } from "./useManagementScope";
import { labels, useManagedOperation } from "./useManagedOperation";

export function PendingManagement({
  account,
  changed,
}: {
  account?: AccountState;
  changed: () => void;
}) {
  const operation = useManagedOperation(account, changed);
  const entries = Object.entries(operation.pending);
  if (!entries.length) return null;
  return (
    <section className="settings-section">
      <h2>待确认操作</h2>
      <Notice tone="warning">
        以下操作尚未收到确定结果，继续前请核对原请求。
      </Notice>
      {entries.map(([id, kind]) => (
        <div className="settings-row" key={id}>
          <span>{labels[kind as ManagementInput["kind"]]}</span>
          <span className="muted">结果待确认</span>
          <div className="inline-actions">
            <Button
              disabled={!account}
              loading={operation.action.busy}
              onClick={() => void operation.reconcile(id, kind)}
            >
              核对原操作
            </Button>
            {kind === "download-update" && (
              <Button
                disabled={!account}
                loading={operation.action.busy}
                onClick={() => void operation.reconcile(id, kind, true)}
              >
                取消下载
              </Button>
            )}
          </div>
        </div>
      ))}
      {operation.action.error && (
        <Notice tone="error">{operation.action.error}</Notice>
      )}
    </section>
  );
}

export function ManagementAction({
  account,
  kind,
  version,
  content,
  changed,
}: {
  account?: AccountState;
  kind: ManagementInput["kind"];
  version?: string;
  content?: string;
  changed: () => void;
}) {
  const { service, session } = useApp();
  const management = service.management ?? unavailableManagement;
  const prepare = useAction();
  const operation = useManagedOperation(account, changed);
  const [plan, setPlan] = useState<ManagementPlan | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [now, setNow] = useState(Date.now());
  const planRevision = useRef<object | null>(null);
  const scope = useManagementScope(
    account,
    JSON.stringify([kind, version, content]),
  );
  const revision = scope.key;
  const latest = useRef(revision);
  latest.current = revision;
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  useEffect(() => {
    setPlan(null);
    setAccepted(false);
  }, [scope.identity]);
  useEffect(() => {
    if (!plan) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [plan]);
  const expired = !!plan && new Date(plan.expiresAt).getTime() <= now;
  const getPlan = async () => {
    const captured = revision;
    setPlan(null);
    setAccepted(false);
    await prepare.run(() =>
      scope.run(async () => {
        if (!account || !session.authenticated)
          throw new Error("账号与数据管理服务尚未接通，当前没有执行更改。");
        if (kind === "restore") {
          if (!content) throw new Error("请先选择备份文件。");
          if (readBackup(content).spaceId !== account.spaceId)
            throw new Error("备份属于其他客户空间，不能在当前空间恢复。");
        }
        const input: ManagementInput = {
          kind,
          spaceId: account.spaceId,
          revision: account.revision,
          deviceId: account.device.id,
          ...(version ? { targetVersion: version } : {}),
          ...(content ? { fileHash: await digest(content) } : {}),
        };
        const hash = await inputDigest(input);
        // Hashing can yield while a dialog closes or the authenticated space changes.
        // Never upload the old backup after that boundary.
        if (!scope.current()) return;
        const proposed = planSchema.parse(
          await managementRequest(() =>
            management.prepare(input, hash, content),
          ),
        );
        if (!scope.current()) return;
        if (
          proposed.kind !== kind ||
          proposed.spaceId !== account.spaceId ||
          proposed.revision !== account.revision ||
          proposed.inputHash !== hash ||
          new Date(proposed.expiresAt).getTime() <= Date.now()
        )
          throw new Error("确认预览已失效或与当前操作不匹配，请重新检查。");
        if (scope.current() && latest.current === captured) {
          planRevision.current = scope.identity;
          setNow(Date.now());
          setPlan(proposed);
        }
      }),
    );
  };
  const execute = async () => {
    if (
      !plan ||
      !accepted ||
      !scope.current() ||
      new Date(plan.expiresAt).getTime() <= Date.now() ||
      planRevision.current !== scope.identity ||
      !account ||
      plan.revision !== account.revision
    )
      return;
    const result = await operation.execute(plan);
    if (
      scope.current() &&
      result &&
      ["SUCCEEDED", "FAILED", "CANCELLED"].includes(result.status)
    ) {
      setPlan(null);
      setAccepted(false);
    }
  };
  return (
    <div className="management-action">
      {!service.management && (
        <Notice tone="warning">
          账号与数据管理服务尚未接通，当前没有执行更改。
        </Notice>
      )}
      {account && (
        <dl className="detail-list">
          <div>
            <dt>客户空间</dt>
            <dd>{account.spaceName}</dd>
          </div>
          <div>
            <dt>本机设备</dt>
            <dd>{account.device.name}</dd>
          </div>
          {version && (
            <div>
              <dt>目标版本</dt>
              <dd>{version}</dd>
            </div>
          )}
        </dl>
      )}
      {!!Object.keys(operation.pending).length && (
        <Notice tone="warning">
          已有操作待确认，请关闭此窗口并核对原操作。
        </Notice>
      )}
      {plan && (
        <>
          <Notice>{plan.summary}</Notice>
          {plan.changes.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>影响范围</th>
                    <th>新增</th>
                    <th>更新</th>
                    <th>移除</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.changes.map((row, i) => (
                    <tr key={i}>
                      <td>{row.label}</td>
                      <td>{row.added}</td>
                      <td>{row.updated}</td>
                      <td>{row.removed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="field-hint">
            确认有效至 {new Date(plan.expiresAt).toLocaleString("zh-CN")}
          </p>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={accepted}
              disabled={expired || operation.action.busy}
              onChange={(e) => setAccepted(e.target.checked)}
            />
            我已核对客户空间、目标及影响范围，确认{labels[kind]}
          </label>
          {expired && (
            <Notice tone="warning">确认预览已过期，请重新检查。</Notice>
          )}
        </>
      )}
      {prepare.error && <Notice tone="error">{prepare.error}</Notice>}
      {operation.action.error && (
        <Notice tone="error">{operation.action.error}</Notice>
      )}
      <div className="inline-actions">
        <Button
          loading={prepare.busy}
          disabled={
            operation.action.busy || !!Object.keys(operation.pending).length
          }
          onClick={() => void getPlan()}
        >
          {plan ? "重新检查影响" : "检查影响并预览"}
        </Button>
        {plan && (
          <Button
            variant={
              kind === "restore" ||
              kind === "unbind-device" ||
              kind === "rollback"
                ? "danger"
                : "primary"
            }
            disabled={
              !accepted || expired || !!Object.keys(operation.pending).length
            }
            loading={operation.action.busy}
            onClick={() => void execute()}
          >
            {labels[kind]}
          </Button>
        )}
      </div>
    </div>
  );
}

export function UpdateManagement({
  account,
  changed,
}: {
  account?: AccountState;
  changed: () => void;
}) {
  const { service } = useApp();
  const updates = useResource(async () => {
    const value = service.management
      ? await managementRequest(() => service.management!.updates())
      : {
          ...(await managementRequest(() => service.checkUpdate())),
          download: "NONE",
        };
    return updateSchema.parse(value);
  }, [service, account?.spaceId]);
  const afterChange = () => {
    changed();
    void updates.reload();
  };
  return (
    <>
      <ResourceStatus
        loading={updates.loading}
        error={updates.error}
        onRetry={() => void updates.reload()}
      />
      {updates.data && (
        <>
          <Notice>
            {updates.data.available
              ? `发现新版本 ${updates.data.version}`
              : "未发现可用更新。"}
          </Notice>
          {updates.data.notes && <p>{updates.data.notes}</p>}
          {updates.data.download === "DOWNLOADING" && (
            <>
              <p role="status">
                安装包正在下载
                {updates.data.progress !== undefined
                  ? `：${updates.data.progress}%`
                  : "…"}
              </p>
              <Button onClick={() => void updates.reload()}>
                刷新下载状态
              </Button>
            </>
          )}
          {updates.data.download === "FAILED" && (
            <Notice tone="error">安装包下载失败，可重新检查后重试。</Notice>
          )}
          {updates.data.available &&
            updates.data.download !== "DOWNLOADING" && (
              <ManagementAction
                account={account}
                kind={
                  updates.data.download === "READY"
                    ? "install-update"
                    : "download-update"
                }
                version={updates.data.version}
                changed={afterChange}
              />
            )}
          {updates.data.rollbackVersion && (
            <>
              <hr />
              <h3>回退至上一版本</h3>
              <ManagementAction
                account={account}
                kind="rollback"
                version={updates.data.rollbackVersion}
                changed={afterChange}
              />
            </>
          )}
        </>
      )}
    </>
  );
}

export function CustomerDataActions({
  account,
  backup,
  changed,
}: {
  account?: AccountState;
  backup: boolean;
  changed: () => void;
}) {
  const { service, session, notify } = useApp();
  const management = service.management ?? unavailableManagement;
  const save = useAction();
  const fileRead = useAction();
  const [content, setContent] = useState<string>();
  const [fileName, setFileName] = useState("");
  const readGeneration = useRef(0);
  const scope = useManagementScope(account, String(backup));
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      readGeneration.current++;
    };
  }, []);
  useEffect(() => {
    readGeneration.current++;
    setContent(undefined);
    setFileName("");
    fileRead.setError("");
    save.setError("");
  }, [scope.identity]);
  const saveFile = async () => {
    await save.run(() =>
      scope.run(async () => {
        if (!account || !session.authenticated)
          throw new Error("客户数据导出服务尚未接通，当前没有生成导出文件。");
        const kind = backup ? "backup-json" : "csv";
        const result = await managementRequest(() =>
          management.exportData(kind),
        );
        if (!scope.current()) return;
        if (result.spaceId !== account.spaceId)
          throw new Error("导出结果与当前客户空间不匹配。");
        if (backup && readBackup(result.content).spaceId !== account.spaceId)
          throw new Error("备份与当前客户空间不匹配。");
        if (!scope.current()) return;
        const saved = await downloadText({
          format: kind,
          name: result.name,
          content: result.content,
        });
        if (!scope.current()) return;
        if (saved.status === "error")
          throw new Error(downloadErrorMessage(saved.error));
        if (saved.status === "saved")
          notify(
            backup ? "客户数据备份已保存。" : "客户数据导出文件已保存。",
            "success",
          );
        if (saved.status === "initiated")
          notify("下载已发起，请在浏览器下载列表中确认文件。", "info");
      }),
    );
  };
  return (
    <>
      {account ? (
        <p>当前客户空间：{account.spaceName}</p>
      ) : service.management ? (
        <Notice>尚未读取到客户空间，请关闭窗口并检查账号状态。</Notice>
      ) : (
        <Notice tone="warning">
          {backup
            ? "客户数据恢复服务尚未接通，当前没有执行覆盖或恢复。"
            : "客户数据导出服务尚未接通，当前没有生成导出文件。"}
        </Notice>
      )}
      <Button
        variant="primary"
        loading={save.busy}
        onClick={() => void saveFile()}
      >
        {backup ? "保存客户数据备份" : "生成并保存 CSV"}
      </Button>
      {save.error && <Notice tone="error">{save.error}</Notice>}
      {backup && (
        <>
          <hr />
          <h3>从备份恢复</h3>
          <Field
            label="客户数据备份"
            hint="选择 .yike-backup.json 文件，最大 2 MB。先检查覆盖范围，再确认恢复。"
          >
            <input
              aria-label="客户数据备份"
              type="file"
              disabled={fileRead.busy || !account}
              accept=".yike-backup.json,application/json"
              onChange={(e) => {
                const file = e.target.files?.[0];
                const generation = ++readGeneration.current;
                setContent(undefined);
                setFileName("");
                fileRead.setError("");
                if (!file) return;
                void fileRead.run(() =>
                  scope.run(async () => {
                    if (
                      !file.name.endsWith(".yike-backup.json") ||
                      file.size > 2 * 1024 * 1024
                    )
                      throw new Error(
                        "请选择不超过 2 MB 的 .yike-backup.json 文件。",
                      );
                    const value = await file.text();
                    if (
                      !scope.current() ||
                      generation !== readGeneration.current
                    )
                      return;
                    const parsed = readBackup(value);
                    if (!account || parsed.spaceId !== account.spaceId)
                      throw new Error("备份与当前客户空间不匹配，不能恢复。");
                    if (live.current && generation === readGeneration.current) {
                      setContent(value);
                      setFileName(file.name);
                    }
                  }),
                );
              }}
            />
          </Field>
          {fileRead.busy && <p role="status">正在检查备份…</p>}
          {fileRead.error && <Notice tone="error">{fileRead.error}</Notice>}
          {fileName && <p className="field-hint">已选择：{fileName}</p>}
          {content && (
            <ManagementAction
              key={fileName + content.length}
              account={account}
              kind="restore"
              content={content}
              changed={changed}
            />
          )}
        </>
      )}
    </>
  );
}
