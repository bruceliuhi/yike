import { useState } from "react";
import { useApp } from "../app/context";
import { useResource } from "../app/hooks";
import { boundedRequest } from "../app/boundedRequest";
import { Badge, Button, Empty, Notice, ResourceStatus, formatDate } from "../components/ui";
import { OUTREACH_QUEUE_LABELS, parseOutreachQueue, type OutreachQueue as Queue } from "../domain/outreach";
import { requireOutreach } from "../services/outreach";

/** Queue records remain distinct from opportunity IDs and never become send authority. */
export function OutreachQueue({ queue, onOpen }: { queue: Queue; onOpen?: (path: string) => void }) {
  const { service, session, navigate } = useApp();
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const resource = useResource(async () => {
    if (!session.authenticated) return undefined;
    try {
      return parseOutreachQueue(await boundedRequest(() => requireOutreach(service.outreach).queue(queue), {timeoutMessage: "触达队列读取超时，请刷新重试。"}), queue);
    } catch (error) {
      if (error instanceof Error && error.name === "ZodError")
        throw new Error("触达队列返回了无效记录，请刷新重试。");
      throw error;
    }
  }, [service, session.authenticated, session.userId, queue]);
  const rows = (resource.data?.items || []).filter((row) =>
    [row.title, row.recipientLabel].join(" ").toLowerCase().includes(query.trim().toLowerCase()),
  ).sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
  const selected = rows.find((r) => r.id === selectedId);
  if (!session.authenticated) return <Empty title="登录后查看客户触达记录" action={<Button onClick={() => navigate("/login")}>登录客户空间</Button>} />;
  return <section aria-label={OUTREACH_QUEUE_LABELS[queue] + "队列"}>
    <div className="section-heading"><h2>{OUTREACH_QUEUE_LABELS[queue]}</h2><Button loading={resource.loading} onClick={resource.reload}>刷新记录</Button></div>
    <ResourceStatus loading={resource.loading} error={resource.error} onRetry={resource.reload} />
    {!resource.loading && !resource.error && resource.data && <>
      <div className="search-input"><input aria-label="搜索触达记录" placeholder="搜索商机或收件对象" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
      {!rows.length ? <Empty title={query ? "没有匹配的记录" : `暂无${OUTREACH_QUEUE_LABELS[queue]}记录`} /> :
        <div className="outreach-layout outreach-queue-layout">
          <aside className="draft-list">{rows.map((row) => <button key={row.id} className={`list-item ${row.id === selectedId ? "selected" : ""}`} onClick={() => setSelectedId(row.id)}>
            <strong>{row.title}</strong><span>{row.recipientLabel || "收件对象待核对"} · {row.channel === "comment" ? "评论" : "私信"}</span>
            <small>{formatDate(row.updatedAt)}</small>{(row.sample || row.id === "sample" || row.opportunityId === "sample") && <Badge tone="orange">公开样例 · 只读</Badge>}
          </button>)}</aside>
          {selected ? <section className="contact-editor" key={selected.id}>
            <div className="section-heading"><h2>{selected.title}</h2><Badge>{OUTREACH_QUEUE_LABELS[queue]}</Badge></div>
            <dl className="detail-list"><div><dt>收件对象</dt><dd>{selected.recipientLabel || "待核对"}</dd></div><div><dt>渠道</dt><dd>{selected.channel === "comment" ? "评论" : "私信"}</dd></div></dl>
            <pre className="draft-preview">{selected.content || "暂无内容"}</pre>
            {selected.message && <Notice>{selected.message}</Notice>}
            {selected.sample || selected.id === "sample" || selected.opportunityId === "sample" ? <Notice>样例记录仅供查看，不能进入客户发送流程。</Notice> : <Button onClick={() => (onOpen || navigate)("/outreach?opportunity=" + encodeURIComponent(selected.opportunityId) + "&channel=" + selected.channel)}>查看联系准备</Button>}
          </section> : <Empty title="选择一条触达记录" />}
        </div>}
    </>}
  </section>;
}
