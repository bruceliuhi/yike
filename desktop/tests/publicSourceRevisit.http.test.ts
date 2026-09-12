/** Local authenticated HTTPS + restricted PG, with synthetic business/source data. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {expect,it} from 'vitest';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {parseExecutionReceipt} from '../src/shared/executionReceipt';
import {candidateSubmissionSchema} from '../src/shared/candidateSubmission';
import {parseCandidateReceipt} from '../src/shared/candidateReceipt';
const artifactPath=process.env.YIKE_PUBLIC_REVISIT_HTTP_ARTIFACT;
function canonical(value:any):string{return Array.isArray(value)?'['+value.map(canonical).join(',')+']':value&&typeof value==='object'
 ?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);}
it.skipIf(!artifactPath)('formal desktop accepts actual v2 HTTPS CLAIM/READ/UNAVAILABLE and Python fingerprints',()=>{
 const artifact=JSON.parse(readFileSync(artifactPath!,'utf8'));expect(Array.isArray(artifact.events)).toBe(true);
 let claims=0,read=0,unavailable=0;const frozen=new Map<string,{topic_id:string;query:string}>();
 for(const event of artifact.events){
  if(event.kind==='execution'){
   const request=executionOperationSchema.parse(event.request),receipt=parseExecutionReceipt(event.receipt,request);
   if(receipt.operation==='CLAIM'&&receipt.public_sampling?.schema_version==='public-sampling-round-v2'){
    claims++;if(receipt.public_sampling.revisit)frozen.set(receipt.request_id,receipt.public_sampling.revisit);
   }
  }else if(event.kind==='candidate'){
   const batch=candidateSubmissionSchema.parse(event.request),receipt=parseCandidateReceipt(event.receipt,batch);
   const {request_id:_,...hashed}=batch;
   expect(createHash('sha256').update(canonical(hashed)).digest('hex')).toBe(event.prepared.batch_fingerprint);
   if(batch.public_revisit){
    expect(receipt.public_revisit).toEqual(batch.public_revisit);
    expect(frozen.get(batch.public_revisit.claim_request_id)?.topic_id).toBe(batch.public_revisit.topic_id);
    if(batch.public_revisit.outcome==='READ'){
     read++;expect(batch.records.find(r=>r.external_source_id===batch.public_revisit!.topic_id)?.query).toBe(frozen.get(batch.public_revisit.claim_request_id)?.query);
    }else unavailable++;
   }
  }else throw new Error('unexpected HTTP artifact event');
 }
 expect(claims).toBeGreaterThanOrEqual(3);expect(read).toBeGreaterThan(0);expect(unavailable).toBeGreaterThan(0);
});
