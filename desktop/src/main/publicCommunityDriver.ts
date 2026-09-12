import type {CollectionDriver} from './collectionWorker';
import {candidateSubmissionSchema,type CandidateSubmission} from '../shared/candidateSubmission';
import {strategyConfigurationSchema} from '../shared/researchStrategies';
import {executionReceiptSchema} from '../shared/executionReceipt';
import {PUBLIC_SOURCES,publicSourceIdSchema,type PublicSourceId} from '../shared/publicSources';
import {sourceContextSchema} from '../shared/publicAuthorContext';

const BYTE_LIMIT=1024*1024;
const fail=(code='PUBLIC_SOURCE_FAILED')=>new Error(code);
const positive=(value:unknown,max=Number.MAX_SAFE_INTEGER):value is number=>
  typeof value==='number' && Number.isSafeInteger(value) && value>0 && value<=max;
const fold=(value:string)=>value.normalize('NFC').toLowerCase();
const timestamp=(value:number)=>new Date(value).toISOString().replace(/\.\d{3}Z$/,'Z');

function sampledTopics(value:any[],maximum:number,round?:number):any[] {
  if(round===undefined||value.length<=maximum)return value.slice(0,maximum);
  const tail=value.length-1;
  if(maximum===1)return [value[round%2===0?0:1+Math.floor(round/2)%tail]];
  const start=round*(maximum-1)%tail;
  return [value[0],...Array.from({length:maximum-1},(_,index)=>value[1+(start+index)%tail])];
}

function recordsFrom(value:unknown,keywords:string[],exclusions:string[],maximum:number,observed:number,sourceId:PublicSourceId,round?:number):CandidateSubmission['records'] {
  if(!Array.isArray(value)||value.length>100)throw fail();
  const records:CandidateSubmission['records']=[],seen=new Set<number>();
  // The budget bounds inspected topics, not just matches. This is a recent
  // endpoint sample: rotation covers the current index, not off-index history.
  // Sampling is before filtering and never refills excluded records.
  for(const topic of sampledTopics(value,maximum,round)) {
    if(!topic||typeof topic!=='object'||!positive(topic.id)||seen.has(topic.id))throw fail();
    if(sourceId==='v2ex-qna-v1'&&topic.node?.name!=='qna')throw fail();
    if(sourceId==='v2ex-outsourcing-authors-v1'&&topic.node?.name!=='outsourcing')throw fail();
    seen.add(topic.id);
    if(topic.deleted===1||topic.deleted===true)continue;
    if(topic.deleted!==0 && topic.deleted!==false && topic.deleted!==undefined)throw fail();
    if(typeof topic.title!=='string'||typeof topic.content!=='string'||!positive(topic.created)||
        topic.created*1000>observed||typeof topic.url!=='string')throw fail();
    const url=new URL(topic.url);
    if(!['http:','https:'].includes(url.protocol)||url.hostname!=='www.v2ex.com'||url.port||url.username||url.password||
        url.search||url.pathname!==`/t/${topic.id}`||url.hash && !/^#reply\d+$/.test(url.hash))throw fail();
    if(!topic.content.trim())continue;
    const fields=[fold(topic.title),fold(topic.content)];
    const query=keywords.find(term=>fields.some(field=>field.includes(fold(term))));
    if(!query||exclusions.some(term=>fields.some(field=>field.includes(fold(term)))))continue;
    if(topic.member?.id!==undefined && !positive(topic.member.id))throw fail();
    records.push({kind:'PAGE',external_source_id:String(topic.id),external_comment_id:null,
      public_url:`https://www.v2ex.com/t/${topic.id}`,title:topic.title||null,body:topic.content,
      author_public_id:topic.member?.id===undefined?null:String(topic.member.id),
      published_at:timestamp(topic.created*1000),observed_at:timestamp(observed),parent:null,
      collector_version:sourceId,normalizer_version:'v2ex-page-v1',query});
  }
  return candidateSubmissionSchema.shape.records.parse(records);
}

function authorContext(topic:any,value:unknown,observed:number){
  if(!positive(topic.member?.id)||!Array.isArray(value)||value.length>100)throw fail();
  const expected=topic.replies===undefined?null:topic.replies;
  if(expected!==null&&(!Number.isSafeInteger(expected)||expected<0||expected>2147483647))throw fail();
  const seen=new Set<number>();const replies=[];
  for(const reply of value){
    if(!reply||typeof reply!=='object'||!positive(reply.id)||seen.has(reply.id)||reply.topic_id!==topic.id||
      !positive(reply.member?.id)||reply.member_id!==undefined&&reply.member_id!==reply.member.id||
      !positive(reply.created)||reply.created<topic.created||reply.created*1000>observed||typeof reply.content!=='string')throw fail();
    seen.add(reply.id);
    if(reply.member.id===topic.member.id)replies.push({id:String(reply.id),body:reply.content,published_at:timestamp(reply.created*1000)});
  }
  return sourceContextSchema.parse({schema_version:'v2ex-author-context-v1',replies_expected:expected,replies_read:value.length,
    replies_complete:expected!==null&&expected===value.length,supplements_read:false,author_replies:replies});
}

/** Main-owned fixed anonymous source, explicitly opted in by a confirmed task. */
export function createPublicCommunityDriver(options:{fetch?:typeof fetch;now?:()=>number}={}):CollectionDriver {
  const fetcher=options.fetch??globalThis.fetch,now=options.now??Date.now;
  // One instance is shared across this controller's tasks, including failures.
  // This local cooldown does not promise a quota across devices sharing an IP.
  let nextRequestAt=0;
  return {start(original) {
    const input=structuredClone({snapshot:original.snapshot,target:original.target,lease:original.lease,maxRecords:original.maxRecords,
      ...(original.allowMonitor===true?{allowMonitor:true as const}:{})});
    const abort=new AbortController();
    let cancelled=original.signal.aborted,timedOut=false,finished=false;
    let timer:ReturnType<typeof setTimeout>|undefined;
    const stopRequest=()=>{cancelled=true;abort.abort();};
    original.signal.addEventListener('abort',stopRequest,{once:true});
    const completed=Promise.resolve().then(async()=>{
      try {
        let configuration:ReturnType<typeof strategyConfigurationSchema.parse>;
        let sourceId:PublicSourceId,endpoint:string;
        let deadline:number,round:number|undefined;
        try {
          const {snapshot,target,maxRecords}=input;
          configuration=strategyConfigurationSchema.parse(snapshot.configuration);
          sourceId=publicSourceIdSchema.parse(configuration.publicSource);endpoint=PUBLIC_SOURCES[sourceId].endpoint;
          const lease=executionReceiptSchema.parse(input.lease);
          const approvedMode=configuration.mode==='once'&&configuration.schedule===null || input.allowMonitor===true&&
            configuration.mode==='monitor'&&configuration.schedule?.policyVersion===1;
          if((lease.operation!=='CLAIM'&&lease.operation!=='RENEW')||lease.execution_generation!==1||!approvedMode||
              configuration.source!=='search'||
              configuration.links.length||configuration.research!==null||
              target.platform!=='PUBLIC_WEB'||target.access_mode!=='PUBLIC_ANONYMOUS'||target.connection_id!==null||target.connection_version!==null||
              !snapshot.platforms.includes('PUBLIC_WEB')||!positive(maxRecords,100)||!positive(snapshot.max_records,10000)||maxRecords>snapshot.max_records||
              !positive(snapshot.max_runtime_seconds,86400))throw fail();
          if(lease.public_sampling!==undefined){
            if(lease.operation!=='CLAIM'||input.allowMonitor!==true||configuration.mode!=='monitor'||
                lease.public_sampling.source_id!==sourceId)throw fail();
            round=lease.public_sampling.round;
          }
          deadline=Math.min(Date.parse(lease.deadline_at),Date.parse(lease.lease_expires_at),now()+snapshot.max_runtime_seconds*1000,now()+20000);
          if(!Number.isFinite(deadline)||deadline<=now())throw fail();
        }catch {throw fail('PUBLIC_SOURCE_INVALID_INPUT');}
        if(cancelled)throw fail('PUBLIC_SOURCE_CANCELLED');
        if(now()<nextRequestAt)throw fail('PUBLIC_SOURCE_RATE_LIMITED');
        nextRequestAt=now()+60000;
        timer=setTimeout(()=>{timedOut=true;abort.abort();},Math.max(1,deadline-now()));
        try {
          let totalBytes=0;
          const readJSON=async(address:string):Promise<unknown>=>{
          if(abort.signal.aborted||now()>=deadline)throw fail();
          const response=await fetcher(address,{method:'GET',redirect:'error',credentials:'omit',signal:abort.signal,
            headers:{Accept:'application/json','User-Agent':'YikeAI/0.2 (public community reader)'}});
          if(response.status!==200||response.redirected||response.url && response.url!==address||
              !/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type')??'')||!response.body) {
            await response.body?.cancel();throw fail();
          }
          const length=response.headers.get('content-length');
          if(length!==null&&(!/^\d+$/.test(length)||Number(length)>BYTE_LIMIT-totalBytes)) {await response.body.cancel();throw fail();}
          const reader=response.body.getReader(),chunks:Uint8Array[]=[];
          try {
            while(true) {
              if(abort.signal.aborted||now()>=deadline)throw fail();
              const next=await reader.read();if(next.done)break;
              totalBytes+=next.value.byteLength;if(totalBytes>BYTE_LIMIT)throw fail();chunks.push(next.value);
            }
          }finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
          if(abort.signal.aborted||now()>=deadline)throw fail();
          const body=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));
          return JSON.parse(body);
          };
          const payload=await readJSON(endpoint),project=sourceId==='v2ex-outsourcing-authors-v1';
          const records=recordsFrom(payload,configuration.keywords,configuration.exclusions,project?Math.min(3,input.maxRecords):input.maxRecords,now(),sourceId,round);
          if(project){
            for(const record of records){
              const topic=(payload as any[]).find(item=>String(item.id)===record.external_source_id);
              if(!positive(topic?.member?.id))throw fail();
              const replies=await readJSON(`https://www.v2ex.com/api/replies/show.json?topic_id=${topic.id}`);
              record.observed_at=timestamp(now());
              record.source_context=authorContext(topic,replies,now());record.normalizer_version='v2ex-author-page-v1';
            }
          }
          return candidateSubmissionSchema.shape.records.parse(records);
        }catch {
          throw fail(cancelled?'PUBLIC_SOURCE_CANCELLED':timedOut?'PUBLIC_SOURCE_TIMED_OUT':'PUBLIC_SOURCE_FAILED');
        }
      }finally {
        finished=true;if(timer)clearTimeout(timer);original.signal.removeEventListener('abort',stopRequest);
      }
    });
    return {completed,async stop(){if(!finished)stopRequest();await completed.then(()=>{},()=>{});}};
  }};
}
