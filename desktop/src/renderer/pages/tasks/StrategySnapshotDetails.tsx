import {platformSearchKeywords,type StrategyReceipt} from "../../../shared/researchStrategies";
import { DEMAND_TYPES } from "../../domain/researchUsage";
import { industrySourceLabels } from '../../../shared/industryTaskStrategy';
import {PUBLIC_SOURCES} from '../../../shared/publicSources';

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
      <div><dt>本次来源</dt><dd>{config.publicSource
        ? config.mode === "once" ? "本次近期主题筛选" : "近期主题定时抽样"
        : config.source === "search" ? "关键词搜索" : "指定内容链接"}</dd></div>
      {config.publicSource && <div><dt>公开来源标识</dt><dd>{config.publicSource} · {PUBLIC_SOURCES[config.publicSource].label} · V2EX近期主题，{config.mode === "once" ? "本次筛选" : "定时抽样"}，不覆盖历史/全站/评论</dd></div>}
      <div><dt>搜索关键词</dt><dd>{config.keywords.join("、") || "无"}{config.source !== "search" && "（保留但本次不执行）"}</dd></div>
      {config.platformQueries && snapshot.platforms.map(platform=><div key={platform}>
        <dt>{platforms[platform]}实际搜索词</dt><dd>{platformSearchKeywords(config,platform).join('、')}（按本次已确认配置执行）</dd>
      </div>)}
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
      {config.industryStrategy&&<div><dt>行业任务策略</dt><dd>
        <p>{config.industryStrategy.sourceTypes.map(type=>industrySourceLabels[type]).join('、')}</p>
        <p>购买信号</p><ul>{config.industryStrategy.intentSignals.map(value=><li key={value}>{value}</li>)}</ul>
        <p>排除反例</p><ul>{config.industryStrategy.counterSignals.map(value=><li key={value}>{value}</li>)}</ul>
        <p>已绑定本次任务快照，发起候选AI判断时作为研究条件使用，不自动过滤采集内容；不代表已发现买方事实，旧历史判断不会自动重跑。</p>
      </dd></div>}
      <div><dt>执行时长上限</dt><dd>{snapshot.max_runtime_seconds} 秒</dd></div>
      <div><dt>策略标识</dt><dd>{snapshot.strategy_version_id}</dd></div>
      <div><dt>配置摘要</dt><dd>{receipt.configuration_sha256}</dd></div>
      <div><dt>画像摘要</dt><dd>{receipt.profile_sha256}</dd></div>
      <div><dt>原准备请求</dt><dd>{receipt.request_id}</dd></div>
      <div><dt>历史回执</dt><dd>{receipt.state} · {receipt.recorded_at}（含时区；非当前执行许可）</dd></div>
    </dl>
  </details>;
}
