import { useEffect, useState } from "react";
import { useApp } from "../../app/context";
import { useAction } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import {
  Badge,
  Button,
  Confirm,
  Empty,
  Field,
  Notice,
  ResourceStatus,
  Tabs,
  formatDate,
} from "../../components/ui";
import { PlatformLabel } from "../../components/Platform";
import {
  FOLLOWUP_LABELS,
  readReplies,
  readSnapshot,
  type FollowupRecord,
  type FollowupView,
  type LinkedReply,
} from "../../domain/followup";
import { useFollowupOperation } from "./useFollowupOperation";
import { useRelatedReplies } from "./useRelatedReplies";
import { ReplyEvidencePanel } from "./ReplyEvidencePanel";
import type { Opportunity } from "../../domain/models";
import { isSample } from "../Opportunities";
export function RelatedReplies({
  opportunityId,
  choices,
  choicesLoading,
  choicesError,
  onReloadChoices,
  onSelect,
  onResolved,
  records,
  recordsLoading,
  recordsError,
  onCorrect,
  onChanged,
}: {
  opportunityId?: string;
  choices: Opportunity[];
  choicesLoading: boolean;
  choicesError: string;
  onReloadChoices: () => void;
  onSelect: (id?: string) => void;
  onResolved: (opportunity?: Opportunity) => void;
  records: FollowupView[];
  recordsLoading: boolean;
  recordsError: string;
  onCorrect: (record: FollowupRecord) => void;
  onChanged: () => void;
}) {
  const { service, session } = useApp();
  const [tab, setTab] = useState("platform");
  const [showEvidence,setShowEvidence]=useState(false);
  const [voidRecord, setVoidRecord] = useState<FollowupRecord>();
  const [reason, setReason] = useState("");
  const preflight = useAction();
  const operation = useFollowupOperation();
  const { target, replies: resource } = useRelatedReplies(opportunityId);
  useEffect(() => {
    onResolved(target.data);
    return () => onResolved(undefined);
  }, [target.data, onResolved]);
  const manual = records.filter(
    (r) =>
      opportunityId &&
      !r.sample &&
      r.opportunityId !== "sample" &&
      r.opportunityId === opportunityId,
  );
  const blocked = operation.blocked;
  const refresh = () => {
    void resource.reload();
    onChanged();
  };
  const mutate = (
    record: FollowupRecord | LinkedReply,
    action: "void" | "mark-read",
  ) =>
    preflight.run(async () => {
      if (
        !service.followup ||
        !session.authenticated ||
        record.sample ||
        !record.opportunityId ||
        !record.profileVersionId
      )
        throw new Error("当前记录不可修改。");
      if (action === "void" && !reason.trim())
        throw new Error("请填写撤销原因，原记录将保留。");
      const row = await boundedRequest(
        () => service.opportunity(record.opportunityId!),
        { timeoutMessage: "商机核对超时，尚未修改。" },
      );
      if (!operation.current()) return;
      if (
        !row ||
        row.id !== record.opportunityId ||
        isSample(row) ||
        row.profileVersionId !== record.profileVersionId
      )
        throw new Error("商机或画像版本已变化，请刷新后核对。");
      if (action === "void") {
        const snapshot = readSnapshot(
          await boundedRequest(() => service.followup!.list(), {
            timeoutMessage: "原登记核对超时，尚未修改。",
          }),
        );
        if (!operation.current()) return;
        const latest = snapshot.records.find((r) => r.id === record.id);
        if (
          !latest ||
          latest.revision !== record.revision ||
          latest.state !== "ACTIVE"
        )
          throw new Error("原登记已变化，请刷新后核对。");
      } else {
        const replies = readReplies(
          await boundedRequest(() => service.followup!.replies(row.id), {
            timeoutMessage: "原回复核对超时，尚未修改。",
          }),
          row.id,
        );
        if (!operation.current()) return;
        const latest = replies.find((r) => r.id === record.id);
        if (
          !latest ||
          latest.revision !== record.revision ||
          latest.profileVersionId !== row.profileVersionId ||
          !latest.sendRequestId ||
          latest.read
        )
          throw new Error("回复或关联发送记录已变化，请刷新后核对。");
      }
      const result = await operation.run({
        binding: {
          opportunityId: row.id,
          profileVersionId: row.profileVersionId,
          action,
          targetId: record.id,
          targetRevision: record.revision,
          requestId: crypto.randomUUID(),
        },
        reason: action === "void" ? reason.trim() : undefined,
      });
      if (operation.current() && result === "SUCCEEDED") {
        setVoidRecord(undefined);
        setReason("");
        refresh();
      }
      if (result === "FAILED")
        throw new Error("服务已确认操作失败，原记录保留。");
    });
  return (
    <aside className="related-replies">
      <div className="followup-selection">
        <h2>关联回复</h2>
        <Button
          variant="ghost"
          loading={target.loading || resource.loading}
          onClick={() => void (opportunityId ? target.reload() : resource.reload())}
        >
          刷新回复
        </Button>
      </div>
      {session.authenticated && (
        <Field label="查看商机回复">
          <select
            aria-label="查看商机回复"
            value={opportunityId || ""}
            onChange={(event) => onSelect(event.target.value || undefined)}
          >
            <option value="">未匹配回复</option>
            {opportunityId && !choices.some((row) => row.id === opportunityId) && (
              <option value={opportunityId}>
                {target.data?.title || "当前目标商机"}
              </option>
            )}
            {choices.map((row) => <option key={row.id} value={row.id}>{row.title}</option>)}
          </select>
          {choicesLoading && <small>正在读取可选商机…</small>}
          {choicesError && (
            <Notice tone="error">
              {choicesError}
              <Button variant="ghost" onClick={onReloadChoices}>重试商机列表</Button>
            </Notice>
          )}
        </Field>
      )}
      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: "platform", label: "通道回复" },
          { key: "manual", label: "人工登记" },
        ]}
      />
      {session.authenticated && opportunityId && (target.loading || target.error) ? (
        <ResourceStatus loading={target.loading} error={target.error} onRetry={target.reload} />
      ) : tab === "platform" ? (
        !session.authenticated ? (
          <Empty title="登录后查看回复" />
        ) : service.replyEvidence && !service.followup ? (
          target.data && target.data.id === opportunityId && !isSample(target.data) ? (
            <ReplyEvidencePanel
              key={`${session.userId}:${session.accountScope?.id}:${session.accountScope?.version}:${opportunityId}`}
              opportunity={target.data}
            />
          ) : <Empty title="选择商机查看回复证据" />
        ) : !service.followup ? (
          <Empty
            title="回复回流尚未接通"
            description="接通后展示真实渠道回复。"
          />
        ) : (
          <>
            {service.replyEvidence && target.data && (
              <>
                <Button variant="ghost" onClick={()=>setShowEvidence(v=>!v)}>
                  {showEvidence?'收起原始回复证据':'查看原始回复证据与同步'}
                </Button>
                {showEvidence && <ReplyEvidencePanel
                  key={`${session.userId}:${session.accountScope?.id}:${session.accountScope?.version}:${opportunityId}`}
                  opportunity={target.data}
                />}
              </>
            )}
            <ResourceStatus
              loading={resource.loading}
              error={resource.error}
              onRetry={resource.reload}
            />
            {!resource.loading &&
              !resource.error &&
              (resource.data?.length ? (
                <div className="followup-replies">
                  {resource.data.map((reply) => (
                    <article key={reply.id}>
                      <Badge tone={reply.read ? "neutral" : "blue"}>
                        {reply.read ? "已读" : "未读"}（仅意客内）
                      </Badge>{" "}
                      <Badge>
                        <PlatformLabel platform={reply.platform} size={16} />
                      </Badge>
                      {reply.sample && (
                        <Badge tone="orange">公开样例 · 只读</Badge>
                      )}
                      <p className="preserve-lines">{reply.content}</p>
                      <small>{formatDate(reply.receivedAt)}</small>
                      {reply.sendRequestId && (
                        <p className="field-hint">关联发送记录：{reply.sendRequestId}</p>
                      )}
                      {!(reply.opportunityId && reply.sendRequestId) && (
                        <Notice>
                          {reply.unmatchedReason ||
                            "尚未匹配到商机与发送记录，请由渠道服务核对。"}
                        </Notice>
                      )}
                      {!reply.read &&
                        !reply.sample &&
                        reply.opportunityId &&
                        reply.sendRequestId && (
                          <Button
                            variant="ghost"
                            disabled={
                              blocked || preflight.busy || operation.action.busy
                            }
                            onClick={() => void mutate(reply, "mark-read")}
                          >
                            标为已读
                          </Button>
                        )}
                    </article>
                  ))}
                </div>
              ) : (
                <Empty
                  title={opportunityId ? "暂无收到的回复" : "暂无未匹配回复"}
                  description={
                    opportunityId ? undefined : "选择商机查看关联回复。"
                  }
                />
              ))}
          </>
        )
      ) : recordsLoading || recordsError ? (
        <ResourceStatus loading={recordsLoading} error={recordsError} onRetry={onChanged} />
      ) : !opportunityId ? (
        <Empty title="选择商机查看人工登记" />
      ) : manual.length ? (
        <div className="followup-timeline">
          {manual.map((row) => (
            <article key={row.id}>
              <Badge>人工登记</Badge>{" "}
              {row.state !== "ACTIVE" && (
                <Badge tone="orange">
                  {row.state === "VOID" ? "已撤销" : "已纠正"}
                </Badge>
              )}
              <h3>{FOLLOWUP_LABELS[row.status]}</h3>
              <p className="preserve-lines">{row.note}</p>
              <div className="followup-note-meta">
                <small>登记：{formatDate(row.createdAt)}</small>
                {row.occurredAt && (
                  <small>联系：{formatDate(row.occurredAt)}</small>
                )}
                {row.nextStep && <p>下一步：{row.nextStep}</p>}
                {row.nextFollowupAt && (
                  <small>下次跟进：{formatDate(row.nextFollowupAt)}</small>
                )}
                {row.correctsId && <small>已纠正原记录</small>}
                {row.reason && <small>原因：{row.reason}</small>}
              </div>
              {!row.legacy &&
                service.followup &&
                row.state === "ACTIVE" &&
                !row.sample && (
                  <div className="followup-audit-actions">
                    <Button
                      variant="ghost"
                      disabled={blocked}
                      onClick={() => onCorrect(row as FollowupRecord)}
                    >
                      纠正记录
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={blocked}
                      onClick={() => {
                        setVoidRecord(row as FollowupRecord);
                        setReason("");
                      }}
                    >
                      撤销登记
                    </Button>
                  </div>
                )}
              {row.legacy && (
                <p className="muted text-small">
                  旧登记的纠正服务尚未接通；可新增人工登记说明更正事实。
                </p>
              )}
            </article>
          ))}
        </div>
      ) : (
        <Empty title="暂无关联登记" />
      )}
      {(preflight.error || operation.action.error) && (
        <Notice tone="error">
          {preflight.error || operation.action.error}
        </Notice>
      )}
      {voidRecord && (
        <Confirm
          title="撤销这条人工登记？"
          loading={preflight.busy || operation.action.busy}
          onCancel={() => {
            if (!preflight.busy && !operation.action.busy)
              setVoidRecord(undefined);
          }}
          onConfirm={() => void mutate(voidRecord, "void")}
          confirmText="确认撤销"
          danger
        >
          <p>原始内容和撤销原因会保留，不会删除审计记录。</p>
          <Field label="撤销原因" required>
            <textarea
              aria-label="撤销原因"
              maxLength={500}
              value={reason}
              disabled={preflight.busy || operation.action.busy}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        </Confirm>
      )}
    </aside>
  );
}
