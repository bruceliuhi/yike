import type {CollectionDriver} from './collectionWorker';
import {candidateSubmissionSchema,type CandidateSubmission} from '../shared/candidateSubmission';
import {strategyConfigurationSchema} from '../shared/researchStrategies';
import {executionReceiptSchema} from '../shared/executionReceipt';
import {PUBLIC_SOURCES,publicSourceIdSchema,type PublicSourceId} from '../shared/publicSources';

const BYTE_LIMIT=1024*1024;
const fail=(code='PUBLIC_SOURCE_FAILED')=>new Error(code);
const positive=(value:unknown,max=Number.MAX_SAFE_INTEGER):value is number=>
  typeof value==='number' && Number.isSafeInteger(value) && value>0 && value<=max;
const fold=(value:string)=>value.normalize('NFC').toLowerCase();
const timestamp=(value:number)=>new Date(value).toISOString().replace(/\.\d{3}Z$/,'Z');

function recordsFrom(value:unknown,keywords:string[],exclusions:string[],maximum:number,observed:number,sourceId:PublicSourceId):CandidateSubmission['records'] {
  if(!Array.isArray(value)||value.length>100)throw fail();
  const records:CandidateSubmission['records']=[],seen=new Set<number>();
  // The budget bounds inspected topics, not just matches. This is a recent
  // endpoint sample: it does not exhaust history or refill excluded records.
  for(const topic of value.slice(0,maximum)) {
    if(!topic||typeof topic!=='object'||!positive(topic.id)||seen.has(topic.id))throw fail();
    if(sourceId==='v2ex-qna-v1'&&topic.node?.name!=='qna')throw fail();
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
        let deadline:number;
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
          deadline=Math.min(Date.parse(lease.deadline_at),Date.parse(lease.lease_expires_at),now()+snapshot.max_runtime_seconds*1000,now()+20000);
          if(!Number.isFinite(deadline)||deadline<=now())throw fail();
        }catch {throw fail('PUBLIC_SOURCE_INVALID_INPUT');}
        if(cancelled)throw fail('PUBLIC_SOURCE_CANCELLED');
        if(now()<nextRequestAt)throw fail('PUBLIC_SOURCE_RATE_LIMITED');
        nextRequestAt=now()+60000;
        timer=setTimeout(()=>{timedOut=true;abort.abort();},Math.max(1,deadline-now()));
        try {
          const response=await fetcher(endpoint,{method:'GET',redirect:'error',credentials:'omit',signal:abort.signal,
            headers:{Accept:'application/json','User-Agent':'YikeAI/0.2 (public community reader)'}});
          if(response.status!==200||response.redirected||response.url && response.url!==endpoint||
              !/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type')??'')||!response.body) {
            await response.body?.cancel();throw fail();
          }
          const length=response.headers.get('content-length');
          if(length!==null&&(!/^\d+$/.test(length)||Number(length)>BYTE_LIMIT)) {await response.body.cancel();throw fail();}
          const reader=response.body.getReader(),chunks:Uint8Array[]=[];let bytes=0;
          try {
            while(true) {
              if(abort.signal.aborted||now()>=deadline)throw fail();
              const next=await reader.read();if(next.done)break;
              bytes+=next.value.byteLength;if(bytes>BYTE_LIMIT)throw fail();chunks.push(next.value);
            }
          }finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
          if(abort.signal.aborted||now()>=deadline)throw fail();
          const body=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));
          return recordsFrom(JSON.parse(body),configuration.keywords,configuration.exclusions,input.maxRecords,now(),sourceId);
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
