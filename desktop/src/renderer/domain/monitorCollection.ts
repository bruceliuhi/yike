import {strategyReceiptSchema,strategyViewSchema,type StrategyReceipt,type StrategyView} from '../../shared/researchStrategies';
import {monitorCollectionCommandSchema,type MonitorCollectionCommand} from '../../shared/monitorCollection';
import {strategyPrepareRequest} from './researchStrategies';
import {hasForegroundBinding} from './task';
import {validStrategyExecutionLimits} from './strategyExecutionLimits';
import type {TaskDraft,PlatformConnection} from './models';

export function monitorTargets(view:StrategyView,connections:PlatformConnection[],accounts?:TaskDraft['accounts']){
 const strategy=strategyViewSchema.parse(view),snapshot=strategy.snapshot;
 if(strategy.state!=='CONFIRMED' || !strategy.is_current || !strategy.profile_current || !strategy.confirmed_at || strategy.revoked_at ||
  snapshot.configuration.mode!=='monitor' || snapshot.configuration.schedule?.policyVersion!==1 || snapshot.configuration.research!==null)throw new Error('当前监控策略尚未确认或已失效。');
 const codes={XIAOHONGSHU:'xhs',DOUYIN:'douyin',BILIBILI:'bilibili',ZHIHU:'zhihu'} as const;
 const devices=new Set<string>();
 const targets=snapshot.platforms.map(platform=>{
  if(!(platform in codes))throw new Error('该平台的持续监控尚未接通。');
  const code=codes[platform as keyof typeof codes];
  const rows=connections.filter(row=>row.platform===code && hasForegroundBinding(row) && (!accounts || row.accountId===accounts[code]));
  if(rows.length!==1)throw new Error('请先连接并核对每个平台的本机账号。');
  const row=rows[0].registration!;devices.add(row.deviceId);
  return {platform:platform as keyof typeof codes,access_mode:'PLATFORM_ACCOUNT' as const,connection_id:row.connectionId,connection_version:row.version};
 });
 if(devices.size!==1)throw new Error('监控账号必须来自同一台当前设备。');
 return targets;
}
export function monitorCreateCommand(draft:TaskDraft,prepared:StrategyReceipt,view:StrategyView,connections:PlatformConnection[],requestId:string){
 const receipt=strategyReceiptSchema.parse(prepared),limits=validStrategyExecutionLimits(draft.executionLimits);
 if(draft.mode!=='monitor' || draft.research || !limits)throw new Error('请核对监控周期与执行上限。');
 const request=strategyPrepareRequest(draft,receipt.request_id,limits);
 if(receipt.draft_id!==draft.id || receipt.draft_revision!==draft.revision || receipt.profile_version_id!==draft.profileId ||
  receipt.strategy_version_id!==view.strategy_version_id || receipt.configuration_sha256!==view.configuration_sha256 ||
  JSON.stringify(receipt.snapshot.configuration)!==JSON.stringify(request.configuration) ||
  JSON.stringify(receipt.snapshot.platforms)!==JSON.stringify(request.platforms) ||
  receipt.snapshot.max_records!==limits.max_records || receipt.snapshot.max_runtime_seconds!==limits.max_runtime_seconds)throw new Error('任务已变化，请重新确认策略。');
 return monitorCollectionCommandSchema.parse({action:'CREATE',requestId,profileVersionId:receipt.profile_version_id,
  strategyVersionId:receipt.strategy_version_id,targets:monitorTargets(view,connections,draft.accounts),humanConfirmed:true}) as Extract<MonitorCollectionCommand,{action:'CREATE'}>;
}
