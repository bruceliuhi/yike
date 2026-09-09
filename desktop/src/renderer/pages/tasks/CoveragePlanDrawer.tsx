import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useTaskDraft, useTaskLibrary } from "../../app/taskDraft";
import { boundedRequest } from "../../app/boundedRequest";
import { Button, Drawer, Field, Notice } from "../../components/ui";
import { PlatformLabel } from "../../components/Platform";
import type { CoveragePlanRequest } from "../../domain/searchCoverage";
import {
  coveragePlanCurrent,
  draftFromCoverage,
  readCoveragePreview,
  type CoveragePlanPreview,
  type CoveragePreviewRequest,
} from "../../domain/coveragePlan";
import type { TaskDraft } from "../../domain/models";
import { errorMessage } from "../../services/contracts";
import { useTaskScope } from "./useTaskScope";
import { useCoverageAdjustment } from "./useCoverageAdjustment";
import "./coverage-plan.css";

export function CoveragePlanDrawer({
  plan,
  onClose,
}: {
  plan: CoveragePlanRequest;
  onClose: () => void;
}) {
  const { service, session, navigate } = useApp();
  const [currentDraft] = useTaskDraft(
    session.userId,
    "once",
    session.accountScope,
  );
  const [, setLibrary] = useTaskLibrary(session.userId, session.accountScope);
  const [maximum, setMaximum] = useState("");
  const scope = useTaskScope(JSON.stringify([plan, maximum]));
  const [state, setState] = useState<{
    identity: object;
    busy: boolean;
    error: string;
    preview?: CoveragePlanPreview;
    expected?: CoveragePreviewRequest;
  }>({ identity: scope.identity, busy: false, error: "" });
  const abort = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const completed = useRef(false);
  const [confirmed, setConfirmed] = useState(false);
  const [created, setCreated] = useState<TaskDraft | null>(null);
  const [, tick] = useState(0);
  const operation = useCoverageAdjustment(plan.taskId);
  useEffect(() => {
    if (operation.rejectedHash) {
      setConfirmed(false);
      setState((old) => ({ ...old, preview: undefined, expected: undefined }));
    }
  }, [operation.rejectedHash]);
  const shown =
    state.identity === scope.identity
      ? state
      : {
          identity: scope.identity,
          busy: false,
          error: "",
          preview: undefined,
          expected: undefined,
        };
  const previewExpiresAt =
    shown.preview?.kind === "ADJUST_LIMIT"
      ? shown.preview.quote.expiresAt
      : shown.preview?.expiresAt || plan.expiresAt;
  useEffect(() => {
    setConfirmed(false);
    abort.current?.abort();
    generation.current++;
    setState({ identity: scope.identity, busy: false, error: "" });
    return () => {
      abort.current?.abort();
      generation.current++;
    };
  }, [scope.identity]);
  useEffect(() => {
    const timer = setTimeout(
      () => tick((old) => old + 1),
      Math.max(
        0,
        Math.min(Date.parse(previewExpiresAt) - Date.now() + 1, 2147483647),
      ),
    );
    return () => clearTimeout(timer);
  }, [previewExpiresAt]);
  const valid =
    !!shown.preview &&
    coveragePlanCurrent(plan, session) &&
    Date.parse(previewExpiresAt) > Date.now();
  const read = async () => {
    if (
      shown.busy ||
      !coveragePlanCurrent(plan, session) ||
      completed.current ||
      operation.pending.length
    )
      return;
    const run = ++generation.current;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setConfirmed(false);
    setState({ identity: scope.identity, busy: true, error: "" });
    try {
      if (!service.coveragePlans)
        throw new Error(
          "补查与上限调整预览服务尚未接通，原任务和草稿保持不变。",
        );
      const newMaxSoubei =
        plan.kind === "ADJUST_LIMIT" ? Number(maximum) : undefined;
      if (
        plan.kind === "ADJUST_LIMIT" &&
        (!Number.isSafeInteger(newMaxSoubei) ||
          !newMaxSoubei ||
          newMaxSoubei < 1 ||
          newMaxSoubei > 1000000)
      )
        throw new Error("请填写有效的新搜贝上限。");
      const expected: CoveragePreviewRequest = {
        requestId: crypto.randomUUID(),
        plan,
        ...(newMaxSoubei === undefined ? {} : { newMaxSoubei }),
      };
      const raw = await boundedRequest(
        (signal) => service.coveragePlans!.preview(expected, signal),
        {
          signal: controller.signal,
          timeoutMessage: "补查预览读取超时，尚未创建草稿或调整上限。",
        },
      );
      if (!scope.current() || generation.current !== run) return;
      const preview = readCoveragePreview(raw, expected, session);
      setState({
        identity: scope.identity,
        busy: false,
        error: "",
        preview,
        expected,
      });
    } catch (e) {
      if (scope.current() && generation.current === run)
        setState({
          identity: scope.identity,
          busy: false,
          error: errorMessage(e),
        });
    }
  };
  useEffect(() => {
    if (plan.kind === "NEW_DRAFT") void read();
  }, [plan]);
  const create = () => {
    if (
      !confirmed ||
      !valid ||
      !shown.preview ||
      !shown.expected ||
      shown.preview.kind !== "NEW_DRAFT" ||
      completed.current
    )
      return;
    try {
      readCoveragePreview(shown.preview, shown.expected, session);
      const next = draftFromCoverage(shown.preview);
      setLibrary((old) => {
        const preserved = [...old];
        if (
          !preserved.some((item) => item.id === currentDraft.id) &&
          (currentDraft.name.trim() ||
            currentDraft.terms.length ||
            currentDraft.profileId)
        )
          preserved.push(currentDraft);
        return [...preserved, next];
      });
      completed.current = true;
      setCreated(next);
    } catch (e) {
      setState((old) => ({ ...old, error: errorMessage(e) }));
    }
  };
  const preview = shown.preview;
  return (
    <Drawer
      title={
        plan.kind === "NEW_DRAFT" ? "基于未查范围创建草稿" : "调整搜贝上限"
      }
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>
            {created || operation.applied ? "关闭" : "取消"}
          </Button>
          {created ? (
            <Button
              variant="primary"
              onClick={() => {
                onClose();
                navigate(
                  created.mode === "monitor" ? "/monitors" : "/collection",
                );
              }}
            >
              查看本机草稿
            </Button>
          ) : plan.kind === "NEW_DRAFT" ? (
            <Button
              variant="primary"
              disabled={!confirmed || !valid || shown.busy}
              onClick={create}
            >
              创建本机草稿
            </Button>
          ) : (
            <Button
              variant="primary"
              disabled={
                !confirmed ||
                !valid ||
                operation.pending.length > 0 ||
                operation.applied ||
                shown.busy
              }
              loading={operation.busy}
              onClick={() => {
                if (preview && shown.expected)
                  void operation.adjust(preview, shown.expected);
              }}
            >
              确认调整上限
            </Button>
          )}
        </>
      }
    >
      <div className="coverage-plan">
        <p>
          {plan.kind === "NEW_DRAFT"
            ? "原任务已终止。新草稿保留已确认的未查范围，可编辑并单独确认后再启动。"
            : "仅调整本次已确认范围的搜贝上限，不会自动恢复任务。"}
        </p>
        {!coveragePlanCurrent(plan, session) && (
          <Notice tone="warning">
            原覆盖记录已过期或客户空间变化，请关闭并重新读取。
          </Notice>
        )}
        {plan.kind === "ADJUST_LIMIT" && (
          <Field label="新的搜贝上限">
            <input
              aria-label="新的搜贝上限"
              type="number"
              min={1}
              max={1000000}
              value={maximum}
              disabled={
                operation.busy ||
                operation.pending.length > 0 ||
                operation.applied
              }
              onChange={(e) => setMaximum(e.target.value)}
            />
          </Field>
        )}
        {!created && !operation.applied && (
          <Button
            disabled={
              !coveragePlanCurrent(plan, session) ||
              operation.pending.length > 0 ||
              operation.busy
            }
            loading={shown.busy}
            onClick={() => void read()}
          >
            {plan.kind === "NEW_DRAFT" ? "重新读取补查预览" : "读取调整估算"}
          </Button>
        )}
        {shown.busy && (
          <Button variant="ghost" onClick={() => abort.current?.abort()}>
            停止等待
          </Button>
        )}
        {shown.error && <Notice tone="warning">{shown.error}</Notice>}
        {preview && (
          <>
            <h3>确认范围</h3>
            <p className="coverage-plan-scope">{preview.scopeSummary}</p>
            <dl>
              <div>
                <dt>原配置版本</dt>
                <dd>v{plan.configurationRevision}</dd>
              </div>
              <div>
                <dt>画像版本</dt>
                <dd>v{plan.profileVersion}</dd>
              </div>
              {preview.kind === "NEW_DRAFT" ? (
                <>
                  <div>
                    <dt>任务名称</dt>
                    <dd>{preview.draft.name} · 补查</dd>
                  </div>
                  <div>
                    <dt>搜索条件</dt>
                    <dd>
                      {preview.draft.terms
                        .map((term) => term.value)
                        .join("、") || "待填写"}
                    </dd>
                  </div>
                  <div>
                    <dt>平台</dt>
                    <dd>
                      {preview.draft.platforms.map((platform) => (
                        <PlatformLabel key={platform} platform={platform} />
                      ))}
                    </dd>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <dt>原搜贝上限</dt>
                    <dd>{preview.quote.oldMaxSoubei} 搜贝</dd>
                  </div>
                  <div>
                    <dt>新搜贝上限</dt>
                    <dd>{preview.quote.newMaxSoubei} 搜贝</dd>
                  </div>
                  <div>
                    <dt>增加上限</dt>
                    <dd>{preview.quote.additionalSoubei} 搜贝</dd>
                  </div>
                  <div>
                    <dt>预计新增消耗</dt>
                    <dd>
                      {preview.quote.estimatedAdditionalSoubei === null
                        ? "尚未确定"
                        : `${preview.quote.estimatedAdditionalSoubei} 搜贝`}
                    </dd>
                  </div>
                  <div>
                    <dt>原预算版本</dt>
                    <dd>
                      v{preview.quote.budgetRevision} ·{" "}
                      {preview.quote.ruleVersion}
                    </dd>
                  </div>
                </>
              )}
            </dl>
            <p className="field-hint">
              预览有效至 {new Date(previewExpiresAt).toLocaleString("zh-CN")}
            </p>
            {!created && !operation.applied && (
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={
                    !valid || operation.busy || operation.pending.length > 0
                  }
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                我已核对本次范围
                {plan.kind === "ADJUST_LIMIT"
                  ? "、新旧上限与差额"
                  : "，仅创建草稿"}
              </label>
            )}
            {!valid && (
              <Notice tone="warning">本次预览已失效，请重新读取后确认。</Notice>
            )}
          </>
        )}
        {operation.pending.map((key) => (
          <Notice
            key={key}
            tone="warning"
            action={
              <Button
                loading={operation.busy}
                onClick={() => void operation.reconcile(key)}
              >
                核对原上限调整
              </Button>
            }
          >
            调整结果尚未确认，原请求已保留；关闭后仍可从任务详情核对。
          </Notice>
        ))}
        {operation.error && <Notice tone="warning">{operation.error}</Notice>}
        {operation.applied && (
          <Notice>
            上限调整已确认，任务尚未恢复。请刷新任务状态后再决定下一步。
          </Notice>
        )}
        {created && (
          <Notice>
            已创建本机会话草稿「{created.name}
            」。旧任务、当前编辑内容和草稿列表均已保留，尚未启动补查。
          </Notice>
        )}
      </div>
    </Drawer>
  );
}
