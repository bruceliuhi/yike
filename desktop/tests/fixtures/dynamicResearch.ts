// Synthetic transport samples only, not live research or buyer evidence.
export const id=(n:number)=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
export const counts=(succeeded=0)=>({issued:succeeded,pending:0,succeeded,failed:0,unknown:0});
export const dynamicCapability={contractVersion:4,sourceScope:'PUBLIC_WEB_AGENT',sourceLabel:'公开网页自主研究',
  sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1','public-web-agent-v1'],maxPlannedSources:3,
  executionMode:'SERVER_BACKGROUND',limits:{maxSearches:10,maxSources:100,maxModelCalls:20,maxMinutes:30,maxRuntimeSeconds:1800},settlementState:'PENDING'} as const;
export function dynamicStatus(){return {contractVersion:4,taskId:id(1),runId:id(2),phase:'QUEUED',
  sourceScope:'PUBLIC_WEB_AGENT',sourceLabel:'公开网页自主研究',executionMode:'SERVER_BACKGROUND',
  acceptedOriginals:0,analyzedOriginals:0,skippedOriginals:0,candidateIds:[],canAdvance:true,stopCode:null,
  newActionsBlocked:false,effectsPending:false,discovery:{searches:counts(),reads:counts(),unpublishedOriginals:0},
  usage:{sourceReads:counts(),modelCalls:counts(),actualSoubei:null,settlementState:'PENDING'}};}
