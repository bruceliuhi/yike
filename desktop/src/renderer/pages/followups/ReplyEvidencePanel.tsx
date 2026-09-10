import { useEffect, useState } from "react";
import { useApp } from "../../app/context";
import { useResource } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import {
  Badge,
  Empty,
  Notice,
  ResourceStatus,
  formatDate,
} from "../../components/ui";
import {
  readReplyEvidence,
  type ReplyEvidence,
} from "../../../shared/replyEvidence";
import type { Opportunity } from "../../domain/models";
import { isSample } from "../Opportunities";
import { NativeReplySync } from "./NativeReplySync";

const sources = {
  DEVICE_ATTESTED_PLATFORM_REPLY: "设备提交的平台证据",
  OPERATOR_RECORDED: "历史人工录入 · 非设备证明",
  MANUAL_RECORD: "人工登记 · 非平台回复",
};
const platforms = {
  XIAOHONGSHU: "小红书",
  DOUYIN: "抖音",
  BILIBILI: "B站",
  ZHIHU: "知乎",
  PUBLIC_WEB: "公开网页",
};
function Evidence({ row }: { row: ReplyEvidence }) {
  const e = row.event;
  return (
    <article>
      <Badge>{sources[row.verification.authority]}</Badge>{" "}
      <Badge>
        {e.state === "VOID"
          ? "已撤销"
          : e.state === "CORRECTED"
            ? "已更正"
            : "有效记录"}
      </Badge>
      {e.kind === "PLATFORM_REPLY" && (
        <>
          {" "}
          <Badge>
            {platforms[e.platform]} · {e.channel === "dm" ? "私信" : "评论"}
          </Badge>{" "}
          <Badge>
            {e.read_state === "UNKNOWN"
              ? "已读状态未知"
              : e.read_state === "READ"
                ? "已读"
                : "未读"}
          </Badge>
          <p className="muted text-small">对方公开标识：{e.sender_public_id}</p>
        </>
      )}
      <p className="preserve-lines">
        {e.kind === "PLATFORM_REPLY" ? e.body : e.note}
      </p>
      <small>
        {e.kind === "PLATFORM_REPLY" ? "回复时间" : "登记发生时间"}：
        {formatDate(
          e.kind === "PLATFORM_REPLY" ? e.received_at : e.occurred_at,
        )}
      </small>
      <p className="muted text-small">
        保存时间：{formatDate(e.observed_at)} · 修订 {row.revision}
      </p>
      {e.reason && <p>更正/撤销原因：{e.reason}</p>}
      <details>
        <summary>原始关联</summary>
        <p className="muted text-small">
          发送请求：{e.outreach_request_id}
          <br />
          来源：{e.source_id}
          <br />
          原画像版本：{e.profile_version_id}
          <br />
          事件：{e.event_id}
        </p>
      </details>
    </article>
  );
}

/** Reads saved evidence only: never syncs an inbox, marks read, or sends. */
export function ReplyEvidencePanel({
  opportunity,
}: {
  opportunity: Opportunity;
}) {
  const { service, session } = useApp();
  const [showHistory, setShowHistory] = useState(false);
  const syncScope = `${session.authenticated}:${session.userId || ""}:${session.accountScope?.id || ""}:${session.accountScope?.version || ""}:${opportunity.id}`;
  const [syncSource, setSyncSource] = useState<{
    scope: string;
    evidence: ReplyEvidence[];
  } | null>(null);
  const resource = useResource(
    async (signal) => {
      if (
        !session.authenticated ||
        !session.userId ||
        !session.accountScope ||
        !service.replyEvidence ||
        isSample(opportunity)
      )
        throw new Error("请登录并选择真实商机后查看回复证据。");
      const raw = await boundedRequest(
        () => service.replyEvidence!(opportunity.id, signal),
        {
          signal,
          timeoutMessage: "回复证据读取超时，请重试。",
        },
      );
      return readReplyEvidence(raw, {
        userId: session.userId,
        tenantId: session.accountScope.id,
        opportunityId: opportunity.id,
      });
    },
    [
      service,
      service.replyEvidence,
      session.authenticated,
      session.userId,
      session.accountScope?.id,
      session.accountScope?.version,
      opportunity,
    ],
  );
  useEffect(() => {
    if (resource.data)
      setSyncSource({ scope: syncScope, evidence: resource.data.history });
  }, [resource.data, syncScope]);
  const syncEvidence = syncSource?.scope === syncScope ? syncSource.evidence : null;
  return (
    <section>
      <ResourceStatus
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {syncEvidence && (
        <NativeReplySync
          session={session}
          opportunity={opportunity}
          evidence={syncEvidence}
          onSynced={resource.reload}
        />
      )}
      {!resource.loading && !resource.error && resource.data && (
        <>
          <Notice>
            这里只展示已保存的证据，不代表已完成平台同步；设备提交证据并非服务器独立平台核验。
          </Notice>
          {!resource.data.history.length ? (
            <Empty
              title="暂无保存的回复证据"
              description="不代表平台没有回复；平台同步状态需另行核对。"
            />
          ) : (
            <>
              <div className="followup-replies">
                {resource.data.replies.map((row) => (
                  <Evidence
                    key={`${row.event.event_id}:${row.revision}`}
                    row={row}
                  />
                ))}
              </div>
              {!!resource.data.manual.length && (
                <details>
                  <summary>人工登记证据</summary>
                  <div className="followup-replies">
                    {resource.data.manual.map((row) => (
                      <Evidence
                        key={`${row.event.event_id}:${row.revision}`}
                        row={row}
                      />
                    ))}
                  </div>
                </details>
              )}
              <details
                onToggle={(event) => setShowHistory(event.currentTarget.open)}
              >
                <summary>完整事件历史</summary>
                {showHistory && (
                  <div className="followup-replies">
                    {resource.data.history.map((row) => (
                      <Evidence
                        key={`${row.event.event_id}:${row.revision}`}
                        row={row}
                      />
                    ))}
                  </div>
                )}
              </details>
            </>
          )}
        </>
      )}
    </section>
  );
}
