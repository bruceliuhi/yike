import {readFileSync} from 'node:fs';
import {expect,it} from 'vitest';

// Guard every customer-facing task surface, including closed details. Payload bindings remain untouched.
const forbidden: Record<string,string[]> = {
 'ResearchProgress.tsx':['<summary>执行明细</summary>','{value.stopCode}</p>'],
 '../../domain/researchProgressPresentation.ts':['查看执行明细','已有结果和执行明细'],
 'TaskProfileStatus.tsx':['任务仍绑定 v','${comparison.bound.version}','${comparison.current.version}'],
 'StrategyConfirmationPanel.tsx':['我已核对以上画像版本'],
 'SearchCoverage.tsx':['本次使用画像 v','{snapshot.window.timezone}）','运行 {snapshot.runId}','{snapshot.deduplicationVersion}'],
 'SearchCoverageDetails.tsx':['查看来源技术信息','{row.ruleVersion}'],
 'ResearchSettings.tsx':['<dt>计量规则</dt>','天 · {value.dynamicScope.timezone}','规划和判断合计'],
 'TaskConfirmationSummary.tsx':['<dt>画像版本</dt>','<dt>时区</dt>','{usage.ruleVersion}','{draft.research.coverageProvenance.runId}','connection?.accountName || selected'],
 'NativeMonitorPlans.tsx':['时区 ${schedule.timezone}','时区 {selected.schedule.timezone}','计划编号：','<p>{command.requestId}</p>','${row.accountId}'],
 'NativeCollectionTasks.tsx':['<summary>原始绑定</summary>','confirmation.item.name || confirmation.item.task_id'],
 'DesktopExecutionRequests.tsx':['<summary>请求详情</summary>','（沿用原请求编号）'],
 'PendingTaskStarts.tsx':['{row.binding.requestId}</p>','配置版本 {row.binding.revision}','<summary>请求详情</summary>','<strong>原请求</strong>'],
 'SearchSuggestionPanel.tsx':['<summary>请求详情</summary>','模型请求可能仍在处理','模型请求或费用已撤销','未调用模型'],
 'TaskDraftRow.tsx':['`${draft.profileId}','<dt>时区</dt>'],
 'CoveragePlanDrawer.tsx':['<dt>原配置版本</dt>','<dt>画像版本</dt>','<dt>原预算版本</dt>'],
 'useTaskActions.tsx':['`任务 ${binding.taskId}`','{binding.requestId}</p>'],
 '../Tasks.tsx':['run.profileName || run.profileId','<dt>画像版本</dt>','<dt>时区</dt>'],
 '../TaskWizard.tsx':['已确认版本 v${selectedProfile.version}','{c.accountName || c.accountId}','设备 {c.registration!.deviceId.slice'],
};
for(const [file,fragments] of Object.entries(forbidden))it(`removes technical customer copy from ${file}`,()=>{
 const source=readFileSync(new URL(`../../src/renderer/pages/tasks/${file}`,import.meta.url),'utf8');
 for(const fragment of fragments)expect(source).not.toContain(fragment);
});
