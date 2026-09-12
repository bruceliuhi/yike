/** Actual local authenticated HTTPS receipts over restricted PostgreSQL, not live platform evidence. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {expect,it} from 'vitest';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {parseExecutionReceipt} from '../src/shared/executionReceipt';
import {candidateSubmissionSchema} from '../src/shared/candidateSubmission';
import {parseCandidateReceipt} from '../src/shared/candidateReceipt';

const artifactPath=process.env.YIKE_NATIVE_PROGRESS_HTTP_ARTIFACT;
function canonical(value:any):string{return Array.isArray(value)?'['+value.map(canonical).join(',')+']':value&&typeof value==='object'
 ?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);}

it.skipIf(!artifactPath)('formal desktop parses server CLAIM/batch echo and matches Python signing fingerprint',()=>{
 const artifact=JSON.parse(readFileSync(artifactPath!,'utf8'));
 expect(Array.isArray(artifact.events)).toBe(true);
 let claims=0,batches=0;
 for(const event of artifact.events){
  if(event.kind==='execution'){
   const request=executionOperationSchema.parse(event.request);
   const receipt=parseExecutionReceipt(event.receipt,request);
   if(receipt.operation==='CLAIM'&&receipt.native_progress)claims++;
  }else if(event.kind==='candidate'){
   const batch=candidateSubmissionSchema.parse(event.request);
   const receipt=parseCandidateReceipt(event.receipt,batch);
   expect(receipt.native_progress).toEqual(batch.native_progress);
   const {request_id:_,...hashed}=batch;
   expect(createHash('sha256').update(canonical(hashed)).digest('hex')).toBe(event.prepared.batch_fingerprint);
   batches++;
  }else throw new Error('unexpected HTTP artifact event');
 }
 expect(claims).toBeGreaterThanOrEqual(2);expect(batches).toBeGreaterThanOrEqual(1);
});
