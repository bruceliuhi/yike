import { useId, useState } from "react";
import { Badge, Button, formatDate } from "../../components/ui";
import { PLATFORMS, type TaskDraft } from "../../domain/models";
export function TaskDraftRow({
  draft,
  pending,
  onEdit,
  onDelete,
  onConfirm,
  onTemplate,
}: {
  draft: TaskDraft;
  pending: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onConfirm: () => void;
  onTemplate?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const region = useId();
  const monitor = draft.mode === "monitor";
  const platforms =
    draft.platforms
      .map((id) => PLATFORMS.find((p) => p.id === id)?.name || id)
      .join("、") || "尚未选择平台";
  return (
    <div className="task-draft-block">
      <article className="task-list-row">
        <div>
          <h3>{draft.name || "未命名任务"}</h3>
          <p>
            {platforms} · {formatDate(draft.savedAt || "")}
          </p>
        </div>
        <Badge tone={pending ? "orange" : "neutral"}>
          {pending ? "启动结果待确认" : "本机草稿 · 未启动"}
        </Badge>
        <div className="inline-actions">
          {monitor && (
            <Button
              variant="ghost"
              aria-expanded={expanded}
              aria-controls={region}
              onClick={() => setExpanded((old) => !old)}
            >
              {expanded ? "收起配置" : "查看配置"}
            </Button>
          )}
          <Button variant="ghost" onClick={onEdit}>
            继续编辑
          </Button>
          {onTemplate && (
            <Button variant="ghost" disabled={pending} onClick={onTemplate}>
              保存为模板
            </Button>
          )}
          <Button variant="ghost" disabled={pending} onClick={onDelete}>
            删除
          </Button>
        </div>
      </article>
      {monitor && expanded && (
        <section
          id={region}
          className="task-draft-config"
          aria-label="监控草稿配置"
        >
          <dl className="task-draft-facts">
            <div>
              <dt>任务名称</dt>
              <dd>{draft.name || "未命名任务"}</dd>
            </div>
            <div>
              <dt>草稿状态</dt>
              <dd>{pending ? "原启动结果待核对" : "本机草稿，尚未启动"}</dd>
            </div>
            <div>
              <dt>业务画像</dt>
              <dd>
                {draft.profileId
                  ? `${draft.profileId}${draft.profileVersion ? ` · v${draft.profileVersion}` : ""}`
                  : "尚未选择画像"}
              </dd>
            </div>
            <div>
              <dt>目标平台</dt>
              <dd>{platforms}</dd>
            </div>
            <div>
              <dt>采集范围</dt>
              <dd>{draft.source === "links" ? "指定链接" : "关键词搜索"}</dd>
            </div>
            <div>
              <dt>{draft.source === "links" ? "指定链接" : "搜索关键词"}</dt>
              <dd>
                {draft.source === "links"
                  ? draft.links || "尚未填写链接"
                  : draft.terms.map((t) => t.value).join("、") || "尚未填写"}
              </dd>
            </div>
            <div>
              <dt>排除词</dt>
              <dd>{draft.exclusions.map((t) => t.value).join("、") || "无"}</dd>
            </div>
            <div>
              <dt>日程频率</dt>
              <dd>
                {draft.schedule.kind === "daily"
                  ? `每日 ${draft.schedule.times.join("、") || "尚未设置时间"}`
                  : `每 ${draft.schedule.interval} 小时 · ${draft.schedule.start}–${draft.schedule.end}`}
              </dd>
            </div>
            <div>
              <dt>时区</dt>
              <dd>{draft.schedule.timezone || "尚未设置"}</dd>
            </div>
          </dl>
          <Button variant="primary" disabled={pending} onClick={onConfirm}>
            前往确认启动
          </Button>
        </section>
      )}
    </div>
  );
}
