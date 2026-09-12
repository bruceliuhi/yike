import type {TaskDraft,Session,PlatformConnection} from './models';
import {configurationHash,hashText} from './taskOperations';
import {parseUsageQuote,usageQuoteRequest,type UsageQuote} from './researchUsage';
import {strategyPrepareRequest} from './researchStrategies';
import {hasPublicSourceBinding} from './task';
import {allowsPublicSource,DEFAULT_PUBLIC_SOURCE,publicSourceIdSchema} from '../../shared/publicSources';
import {researchSources} from '../../shared/researchSourcePlan';
import {DYNAMIC_RESEARCH_SOURCE,dynamicLimitsValid} from '../../shared/dynamicResearch';
import {researchAllowsSelection} from '../../shared/researchRuntime';
import {validStrategyExecutionLimits} from './strategyExecutionLimits';
import {strategyReceiptSchema,type StrategyReceipt} from '../../shared/researchStrategies';
import {desktopExecutionCommandSchema,type DesktopExecutionCommand} from '../../shared/desktopExecution';

export async function nativeResearchStartCommand(draft:TaskDraft,prepared:StrategyReceipt,
  connections:PlatformConnection[],session:Session,quote:UsageQuote,requestId:string,dynamicCapability?:unknown) {
  const limits=validStrategyExecutionLimits(draft.executionLimits),receipt=strategyReceiptSchema.parse(prepared);
  const publicRows=connections.filter(hasPublicSourceBinding);
  const dynamic=draft.publicSource===DYNAMIC_RESEARCH_SOURCE;
  const allowed=dynamic?researchAllowsSelection(dynamicCapability,DYNAMIC_RESEARCH_SOURCE)&&!!draft.research?.dynamicScope&&dynamicLimitsValid(draft.research.limits)
    :publicRows.length===1&&researchSources(publicSourceIdSchema.parse(draft.publicSource??DEFAULT_PUBLIC_SOURCE),draft.research?.sourcePlan)
      .every(source=>allowsPublicSource(source,publicRows[0].publicBinding?.sourceId,publicRows[0].publicBinding?.sourceIds));
  if(!limits || !draft.research || draft.mode!=='once' || draft.platforms.length!==1 || draft.platforms[0]!=='web' ||
    draft.accounts.web || !allowed || limits.max_records>100 || limits.max_runtime_seconds>(dynamic?1800:900))
    throw new Error(dynamic?'请核对公开网页自主研究能力、时效和执行上限。':'研究执行仅支持已核实的V2EX所选板块单次索引研究，请核对范围。');
  const expected=strategyPrepareRequest(draft,receipt.request_id,limits);
  if(receipt.draft_id!==draft.id || receipt.draft_revision!==draft.revision || receipt.profile_version_id!==draft.profileId ||
    JSON.stringify(receipt.snapshot.configuration)!==JSON.stringify(expected.configuration) ||
    JSON.stringify(receipt.snapshot.platforms)!==JSON.stringify(expected.platforms) ||
    receipt.snapshot.max_records!==limits.max_records || receipt.snapshot.max_runtime_seconds!==limits.max_runtime_seconds)
    throw new Error('当前草稿与已确认研究策略不一致，请重新确认。');
  const binding={strategyVersionId:receipt.strategy_version_id,profileVersionId:receipt.profile_version_id,
    configurationSha256:receipt.configuration_sha256};
  const hash=await hashText(JSON.stringify([await configurationHash(draft),draft.executionLimits,binding]));
  const input=usageQuoteRequest(draft,session,hash,binding);
  const fresh=parseUsageQuote(quote,{...input,requestId:quote.requestId});
  return desktopExecutionCommandSchema.parse({action:'RESEARCH_START',humanConfirmed:true,requestId,...binding,
    authorizationToken:fresh.authorizationToken,
    targets:[{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null}],
    reservation:{quote_id:fresh.quoteId,strategy_version_id:binding.strategyVersionId,profile_version_id:binding.profileVersionId,
      configuration_sha256:binding.configurationSha256,rule_version:fresh.ruleVersion,rule_sha256:fresh.ruleSha256,
      estimated_soubei:fresh.estimatedSoubei,max_soubei:fresh.maxSoubei,limits:draft.research.limits},
  }) as Extract<DesktopExecutionCommand,{action:'RESEARCH_START'}>;
}
