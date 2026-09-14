import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {expect,it} from 'vitest';

// Customer-copy regression, not a visual or end-to-end acceptance test.
const retiredCopy:Record<string,string[]>={
  'pages/tasks/ResearchProgress.tsx':['离开页面不会停止服务端研究','停止本页不代表','研究停止不表示费用已结清'],
  'domain/researchProgressPresentation.ts':['本轮存在读取或分析失败记录','尚有请求或执行记录待核实','执行进程是否退出','研究结果传输尚未核实'],
  'pages/tasks/SearchCoverage.tsx':['平台访问、搜贝用量与筛选结果分别记录','各方向计数不跨平台直接相加','不按零消耗处理','未检查、待复核和未知结果分别保留'],
  'pages/workbench/OpportunityBrief.tsx':['查看检查范围与口径','平台连接状态不代表已完成搜索','未检查的范围不代表没有机会'],
  'pages/opportunities/CandidateOriginalEvidence.tsx':['不代表来源当前可访问或已授权联系','不同作者不视为同一人','每条记录保留其自己的原文、版本与时间'],
  'pages/opportunities/CandidateAssessmentDetails.tsx':['再显式发起判断','不是原文事实或发送授权','不会自动填入人工证据'],
  'pages/opportunities/CandidateRequestHistory.tsx':['已取得回执','尚未收到确定回执','核对操作不会重新判断或重复入库'],
  'pages/Followups.tsx':['结构化计划尚未接通'],
  'pages/followups/ReplyEvidencePanel.tsx':['设备提交证据并非服务器独立平台核验','平台同步状态需另行核对'],
  'pages/connections/DisconnectPanel.tsx':['等待断开回执','未撤销服务端请求'],
  'pages/tasks/StrategyConfirmationPanel.tsx':['服务端快照已核对','只在原配置一致时沿用原请求'],
  'pages/tasks/PublicSourceSelector.tsx':['空板块的配额不转移','不会自动切换或启动'],
  'pages/tasks/PlatformSearchTerms.tsx':['不会自动切换任务类型'],
  'pages/tasks/TaskProfileStatus.tsx':['原任务不会自动换版或重新启动'],
  'pages/tasks/PendingTaskStarts.tsx':['仅查询原请求，不会重新创建任务'],
  'pages/tasks/CoverageAdjustmentRecovery.tsx':['仅查询原请求，不会再次调整或恢复任务'],
  'pages/settings/DeviceIdentityPanel.tsx':['设备核验不代表平台已连接或使用授权已激活'],
  'pages/outreach/AdoptedCoachSummary.tsx':['不代表此后发生了新的审核'],
  'pages/outreach/ContactMaterialQuotes.tsx':['历史记录不代表当前仍获授权'],
  'pages/outreach/NativeSendConfirmation.tsx':['准备信息不代表已发送'],
  'pages/Opportunities.tsx':['重复观察按线索去重，不等同于采集入库记录数','打开链接不会自动解除此限制'],
};
it.each(Object.entries(retiredCopy))('removes retired internal explanations from %s',(file,phrases)=>{
  const source=readFileSync(resolve(process.cwd(),'src/renderer',file),'utf8');
  for(const phrase of phrases)expect(source.includes(phrase),`${file}: ${phrase}`).toBe(false);
});
