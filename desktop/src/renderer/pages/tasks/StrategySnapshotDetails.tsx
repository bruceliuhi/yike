import type { StrategyReceipt } from "../../../shared/researchStrategies";
import { DEMAND_TYPES } from "../../domain/researchUsage";

const platforms = { XIAOHONGSHU: "小红书", DOUYIN: "抖音", BILIBILI: "B站", ZHIHU: "知乎", PUBLIC_WEB: "公开网站" };

/** Only receives the controller's strictly bound receipt, never unvalidated wire data. */
export function StrategySnapshotDetails({ receipt }: { receipt: StrategyReceipt }) {
  const snapshot = receipt.snapshot;
  const config = snapshot.configuration;
  const schedule = config.schedule;
  const research = config.research;
  return <details className="strategy-snapshot">
    <summary>全部绑定配置</summary>
    <dl className="detail-list">
      <div><dt>任务名称</dt><dd>{config.name}</dd></div>
      <div><dt>配置格式</dt><dd>{config.schema_version}</dd></div>
      <div><dt>草稿版本</dt><dd>{receipt.draft_id} · 修订 {receipt.draft_revision}</dd></div>
      <div><dt>画像版本标识</dt><dd>{snapshot.profile_version_id}</dd></div>
      <div><dt>本次来源</dt><dd>{config.source === "search" ? "关键词搜索" : "指定内容链接"}</dd></div>
      <div><dt>搜索关键词</dt><dd>{config.keywords.join("、") || "无"}{config.source !== "search" && "（保留但本次不执行）"}</dd></div>
      <div><dt>排除词</dt><dd>{config.exclusions.join("、") || "无"}</dd></div>
      <div><dt>内容链接</dt><dd>{config.links.join("\n") || "无"}{config.source !== "links" && "（保留但本次不执行）"}</dd></div>
      <div><dt>平台顺序</dt><dd>{snapshot.platforms.map(id => platforms[id]).join(" → ")}</dd></div>
      <div><dt>运行方式</dt><dd>{config.mode === "once" ? "单次采集" : "持续监控"}</dd></div>
      <div><dt>保留日程</dt><dd>{!schedule ? "未设置" : <>
        {config.mode === "once" && <p>本次不调度</p>}
        <p>方式：{schedule.kind === "daily" ? "每日" : "间隔"}；每日时刻：{schedule.times.join("、") || "无"}</p>
        <p>间隔：{schedule.interval} 小时；窗口：{schedule.start}–{schedule.end}；时区：{schedule.timezone}</p>
        <p>日程规则版本：{schedule.policyVersion ?? "旧版未标注"}</p>
      </>}</dd></div>
      <div><dt>研究设置</dt><dd>{!research ? "未配置" : <>
        <p>版本：{research.version}；需求类型：{research.demandTypes.map(type => DEMAND_TYPES[type]).join("、")}</p>
        <p>搜贝上限：{research.maxSoubei} 搜贝</p>
        <p>独立来源上限：{research.limits.sources} 条；运行时长上限：{research.limits.minutes} 分钟；模型调用上限：{research.limits.modelCalls} 次</p>
        <p>停止条件：{research.stopAtAnyLimit ? "任一上限触达即停止" : "未确认"}</p>
        <p>补证顺序：原文与发布时间 → 需求依据与目标匹配 → 联系上下文（{research.evidenceOrder}）</p>
      </>}</dd></div>
      <div><dt>执行记录上限</dt><dd>{snapshot.max_records} 条</dd></div>
      <div><dt>执行时长上限</dt><dd>{snapshot.max_runtime_seconds} 秒</dd></div>
      <div><dt>策略标识</dt><dd>{snapshot.strategy_version_id}</dd></div>
      <div><dt>配置摘要</dt><dd>{receipt.configuration_sha256}</dd></div>
      <div><dt>画像摘要</dt><dd>{receipt.profile_sha256}</dd></div>
      <div><dt>原准备请求</dt><dd>{receipt.request_id}</dd></div>
      <div><dt>历史回执</dt><dd>{receipt.state} · {receipt.recorded_at}（含时区；非当前执行许可）</dd></div>
    </dl>
  </details>;
}
