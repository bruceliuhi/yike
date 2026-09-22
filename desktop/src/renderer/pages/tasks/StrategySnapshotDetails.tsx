import {platformSearchKeywords,type StrategyReceipt} from "../../../shared/researchStrategies";
import { DEMAND_TYPES } from "../../domain/researchUsage";
import { industrySourceLabels } from '../../../shared/industryTaskStrategy';
import {researchSelectionScope as publicSourceScope,DYNAMIC_RESEARCH_SOURCE} from '../../../shared/dynamicResearch';
import {scheduleRegionLabel} from './taskDisplayLabels';
import { PlatformLabel } from '../../components/Platform';

/** Only receives the controller's strictly bound receipt, never unvalidated wire data. */
export function StrategySnapshotDetails({ receipt }: { receipt: StrategyReceipt }) {
  const snapshot = receipt.snapshot;
  const config = snapshot.configuration;
  const schedule = config.schedule;
  const research = config.research;
  return <details className="strategy-snapshot">
    <summary>完整任务配置</summary>
    <dl className="detail-list">
      <div><dt>任务名称</dt><dd>{config.name}</dd></div>
      <div><dt>本次来源</dt><dd>{config.publicSource
        ? config.publicSource===DYNAMIC_RESEARCH_SOURCE?'按业务动态搜索公开原文':config.mode === "once" ? "本次近期主题筛选" : "近期主题定时抽样"
        : config.source === "search" ? "关键词搜索" : "指定内容链接"}</dd></div>
      {config.publicSource && <div><dt>公开来源范围</dt><dd>{publicSourceScope(config.publicSource)} · {config.mode === "once" ? "本次筛选" : "定时抽样"}</dd></div>}
      {research?.dynamicScope&&<div><dt>需求时间窗口</dt><dd>近 {research.dynamicScope.maxAgeDays} 天；依据作者原文，非搜索收录日期</dd></div>}
      <div><dt>搜索关键词</dt><dd>{config.keywords.join("、") || "无"}{config.source !== "search" && "（保留但本次不执行）"}</dd></div>
      {config.platformQueries && snapshot.platforms.map(platform=><div key={platform}>
        <dt><PlatformLabel platform={platform} size={16} />实际搜索词</dt><dd>{platformSearchKeywords(config,platform).join('、')}（按本次已确认配置执行）</dd>
      </div>)}
      <div><dt>排除词</dt><dd>{config.exclusions.join("、") || "无"}</dd></div>
      <div><dt>内容链接</dt><dd>{config.links.join("\n") || "无"}{config.source !== "links" && "（保留但本次不执行）"}</dd></div>
      <div><dt>平台顺序</dt><dd className="platform-list">{snapshot.platforms.map((id, index) => <span key={id} className="platform-list-item"><PlatformLabel platform={id} size={16} />{index < snapshot.platforms.length - 1 && <span aria-hidden="true">→</span>}</span>)}</dd></div>
      <div><dt>运行方式</dt><dd>{config.mode === "once" ? "单次采集" : "持续监控"}</dd></div>
      <div><dt>保留日程</dt><dd>{!schedule ? "未设置" : <>
        {config.mode === "once" && <p>本次不调度</p>}
        <p>方式：{schedule.kind === "daily" ? "每日" : "间隔"}；每日时刻：{schedule.times.join("、") || "无"}</p>
        <p>间隔：{schedule.interval} 小时；窗口：{schedule.start}–{schedule.end} · {scheduleRegionLabel(schedule.timezone)}</p>
      </>}</dd></div>
      <div><dt>研究设置</dt><dd>{!research ? "未配置" : <>
        <p>需求类型：{research.demandTypes.map(type => DEMAND_TYPES[type]).join("、")}</p>
        <p>搜贝上限：{research.maxSoubei} 搜贝</p>
        <p>独立来源上限：{research.limits.sources} 条；运行时长上限：{research.limits.minutes} 分钟；模型调用上限：{research.limits.modelCalls} 次</p>
        <p>停止条件：{research.stopAtAnyLimit ? "任一上限触达即停止" : "未确认"}</p>
      </>}</dd></div>
      <div><dt>执行记录上限</dt><dd>{snapshot.max_records} 条</dd></div>
      {config.industryStrategy&&<div><dt>行业任务策略</dt><dd>
        <p>发起候选AI判断时作为研究条件使用，不自动替代人工确认</p>
        <p>{config.industryStrategy.sourceTypes.map(type=>industrySourceLabels[type]).join('、')}</p>
        <p>购买信号</p><ul>{config.industryStrategy.intentSignals.map(value=><li key={value}>{value}</li>)}</ul>
        <p>排除反例</p><ul>{config.industryStrategy.counterSignals.map(value=><li key={value}>{value}</li>)}</ul>
      </dd></div>}
      <div><dt>执行时长上限</dt><dd>{snapshot.max_runtime_seconds} 秒</dd></div>
    </dl>
  </details>;
}
