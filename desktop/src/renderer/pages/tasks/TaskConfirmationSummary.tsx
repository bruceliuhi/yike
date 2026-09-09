import { PlatformLabel } from "../../components/Platform";
import { Badge, Button } from "../../components/ui";
import {
  type PlatformConnection,
  type Profile,
  type TaskDraft,
} from "../../domain/models";
import "./confirmation.css";

export function TaskConfirmationSummary({
  draft,
  profile,
  connections,
  deviceReady,
  disabled,
  onEdit,
}: {
  draft: TaskDraft;
  profile?: Profile;
  connections: PlatformConnection[];
  deviceReady: boolean;
  disabled: boolean;
  onEdit: () => void;
}) {
  const source = draft.source === "search" ? "关键词搜索" : "指定内容链接";
  const hasAI = [...draft.terms, ...draft.exclusions].some(
    (term) => term.origin === "ai",
  );
  const edited = [...draft.terms, ...draft.exclusions].some(
    (term) => term.edited || term.origin !== "ai",
  );
  return (
    <>
      <section className="task-confirm-summary">
        <div className="section-heading">
          <h2>配置摘要</h2>
          <Button variant="ghost" disabled={disabled} onClick={onEdit}>
            修改配置
          </Button>
        </div>
        <div className="task-confirm-columns">
          <dl className="detail-list">
            <div>
              <dt>任务名称</dt>
              <dd>{draft.name || "未填写"}</dd>
            </div>
            <div>
              <dt>业务画像</dt>
              <dd>{profile?.fields.service || "待确认真实画像"}</dd>
            </div>
            <div>
              <dt>画像版本</dt>
              <dd>
                {draft.profileVersion ? `v${draft.profileVersion}` : "未确认"}
              </dd>
            </div>
            <div>
              <dt>执行设备</dt>
              <dd>{deviceReady ? "执行服务已就绪" : "本机 · 待绑定或检查"}</dd>
            </div>
            <div>
              <dt>搜索关键词</dt>
              <dd>
                {draft.terms.map((term) => term.value).join("、") || "未填写"}
              </dd>
            </div>
            {draft.source === "links" && (
              <div>
                <dt>内容链接</dt>
                <dd>{draft.links || "未填写"}</dd>
              </div>
            )}
          </dl>
          <dl className="detail-list">
            <div>
              <dt>来源范围</dt>
              <dd>{source}</dd>
            </div>
            <div>
              <dt>运行方式</dt>
              <dd>{draft.mode === "once" ? "单次采集" : "持续监控"}</dd>
            </div>
            <div>
              <dt>排除词</dt>
              <dd>
                {draft.exclusions.map((term) => term.value).join("、") || "无"}
              </dd>
            </div>
            <div>
              <dt>条件来源</dt>
              <dd>
                {hasAI
                  ? edited
                    ? "AI 建议与人工编辑"
                    : "AI 建议"
                  : "人工配置"}{" "}
                · 可返回修改
              </dd>
            </div>
            {draft.mode === "monitor" && (
              <>
                <div>
                  <dt>执行频率</dt>
                  <dd>
                    {draft.schedule.kind === "daily"
                      ? `每日 ${draft.schedule.times.join("、")}`
                      : `每 ${draft.schedule.interval} 小时`}
                  </dd>
                </div>
                <div>
                  <dt>执行窗口</dt>
                  <dd>
                    {draft.schedule.kind === "interval"
                      ? `${draft.schedule.start}–${draft.schedule.end}`
                      : "按每日设定时间"}
                  </dd>
                </div>
                <div>
                  <dt>时区</dt>
                  <dd>{draft.schedule.timezone}</dd>
                </div>
              </>
            )}
          </dl>
        </div>
      </section>
      <section className="task-confirm-platforms">
        <h2>平台与执行账号</h2>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>平台</th>
                <th>执行账号</th>
                <th>连接状态</th>
                <th>范围</th>
              </tr>
            </thead>
            <tbody>
              {draft.platforms.map((id) => {
                const connection = connections.find(
                  (row) => row.platform === id,
                );
                const selected = draft.accounts[id];
                const matches =
                  !!selected && selected === connection?.accountId;
                const status = connection
                  ? {
                      CONNECTED: "已连接",
                      DISCONNECTED: "未连接",
                      EXPIRED: "登录已过期",
                      LIMITED: "平台限流",
                      UNAVAILABLE: "暂不可用",
                    }[connection.status]
                  : "待核验";
                const webReady =
                  id === "web" &&
                  connection?.status === "CONNECTED" &&
                  connection.capabilities.includes("collect");
                return (
                  <tr key={id}>
                    <td>
                      <span className="task-confirm-platform">
                        <PlatformLabel platform={id} size={20} />
                      </span>
                    </td>
                    <td>
                      {id === "web"
                        ? "无需账号"
                        : matches
                          ? connection?.accountName || selected
                          : selected
                            ? `${selected}（待核对）`
                            : "—"}
                    </td>
                    <td>
                      <Badge
                        tone={
                          (
                            id === "web"
                              ? webReady
                              : matches && connection?.status === "CONNECTED"
                          )
                            ? "green"
                            : "neutral"
                        }
                      >
                        {id === "web"
                          ? webReady
                            ? "公开读取可用"
                            : "范围待确认"
                          : connection?.status === "CONNECTED" && !matches
                            ? selected
                              ? "执行账号待核对"
                              : "待选择执行账号"
                            : status}
                      </Badge>
                    </td>
                    <td>{source}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!draft.platforms.length && <p className="muted">尚未选择平台。</p>}
      </section>
    </>
  );
}
