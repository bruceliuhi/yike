/** Validate observed author changes against retained versions, never model prose. */
import {z} from 'zod';
import {sourceContextSchema,validAuthorTimes} from '../../shared/publicAuthorContext';
import {explicitInstant} from './opportunityLibrary';

const id=z.string().min(1).max(512);
const instant=z.string().refine(explicitInstant);
const sourceUrl=z.string().max(2048).refine(value=>{
 try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password;}catch{return false;}
});
const quote=z.object({sourceUrl,evidenceVersion:id,
 quote:z.string().min(1).max(8000).refine(value=>value.trim().length>0),
}).strict();
export const authorVersionFields={
 authorPublicId:z.string().min(1).max(256).refine(value=>value.trim().length>0).nullable(),
 sourceContext:sourceContextSchema.nullable(),
};
export const authorChangeSchema=z.object({id,replyId:z.string().regex(/^[1-9][0-9]*$/),
 kind:z.enum(['OBSERVED_NEW','MODIFIED']),label:z.string().min(1).max(8000),
 fromObservationId:id,toObservationId:id,detectedAt:instant,occurredAt:z.null(),
 from:quote.nullable(),to:quote,
}).strict();
type Version=z.infer<z.ZodObject<typeof authorVersionFields>>&{
 id:string;content:string;publishedAt:string|null;
};
type Observation={id:string;versionId:string;observedAt:string;receivedAt:string};
type Timeline={versions:Version[];observations:Observation[];anchorObservationId:string;
 binding:{sourceUrl:string};authorChanges:z.infer<typeof authorChangeSchema>[];
 changes:{id:string}[];contacts:{id:string}[];};
function invalid():never{throw new Error('作者变化与留存证据不一致，请刷新重试。');}
const signature=(v:Version)=>JSON.stringify([v.content,v.authorPublicId,
 v.sourceContext===null?null:[...v.sourceContext.author_replies].sort((a,b)=>a.id.localeCompare(b.id))]);

export function validateAuthorChanges(data:Timeline){
 const versions=new Map(data.versions.map(v=>[v.id,v]));
 const observations=new Map(data.observations.map(o=>[o.id,o]));
 const anchor=observations.get(data.anchorObservationId);if(!anchor)invalid();
 const groups:{at:number;rows:Observation[]}[]=[];
 for(const observation of data.observations){
  const v=versions.get(observation.versionId);if(!v)invalid();
  if(!validAuthorTimes(v.sourceContext??undefined,v.publishedAt,observation.observedAt))invalid();
  const at=Date.parse(observation.observedAt);
  if(!groups.length||groups.at(-1)!.at!==at)groups.push({at,rows:[]});
  groups.at(-1)!.rows.push(observation);
 }
 const expected=new Map<string,{before:typeof groups[number];after:typeof groups[number]}>();
 let baseline:typeof groups[number]|null=null;
 const key=(group:number,replyId:string,kind:string)=>JSON.stringify([group,replyId,kind]);
 for(const [index,group] of groups.entries()){
  if(group.at<Date.parse(anchor.observedAt))continue;
  const values=group.rows.map(o=>versions.get(o.versionId)!);
  if(new Set(values.map(signature)).size!==1){baseline=null;continue;}
  const after=values[0];
  if(group.at===Date.parse(anchor.observedAt)){baseline=group;continue;}
  const before=baseline&&versions.get(baseline.rows[0].versionId)!;
  if(before?.sourceContext&&after.sourceContext&&before.authorPublicId&&before.authorPublicId===after.authorPublicId){
   const previous=new Map(before.sourceContext.author_replies.map(r=>[r.id,r.body]));
   for(const reply of after.sourceContext.author_replies){
    const old=previous.get(reply.id);
    if(old===undefined||old!==reply.body)expected.set(key(index,reply.id,old===undefined?'OBSERVED_NEW':'MODIFIED'),
     {before:baseline!,after:group});
   }
  }
  baseline=group;
 }
 const ids=new Set([...data.changes,...data.contacts].map(c=>c.id));
 for(const change of data.authorChanges){
  if(ids.has(change.id))invalid();ids.add(change.id);
  const group=groups.findIndex(g=>g.rows.some(o=>o.id===change.toObservationId));
  const eventKey=key(group,change.replyId,change.kind),pair=expected.get(eventKey);
  const before=observations.get(change.fromObservationId),after=observations.get(change.toObservationId);
  if(!pair||!before||!after||!pair.before.rows.some(o=>o.id===before.id)||!pair.after.rows.some(o=>o.id===after.id)||
   Date.parse(change.detectedAt)!==Math.max(Date.parse(before.receivedAt),Date.parse(after.receivedAt)))invalid();
  const verify=(evidence:z.infer<typeof quote>,observation:Observation)=>{
   const body=versions.get(observation.versionId)?.sourceContext?.author_replies.find(r=>r.id===change.replyId)?.body;
   if(evidence.sourceUrl!==data.binding.sourceUrl||evidence.evidenceVersion!==observation.versionId||
    body===undefined||!body.includes(evidence.quote))invalid();
  };
  if(change.kind==='OBSERVED_NEW'){if(change.from!==null)invalid();}
  else{if(change.from===null)invalid();verify(change.from,before);}
  verify(change.to,after);expected.delete(eventKey);
 }
 if(expected.size)invalid();
}
