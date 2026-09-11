import type {ApiOperation} from '../../shared/contracts';
import {coachInputHash,coachInputSchema,coachGenerateSchema,coachPreviewSchema,coachPolicy} from '../../shared/shortCoach';
import {readCoachSuggestion,textDigest,type CoachInput} from '../domain/shortCoach';
import type {Session} from '../domain/models';
import type {ShortCoachService} from './shortCoach';
type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const identity=(value:Session)=>JSON.stringify([value.authenticated,value.userId,value.accountScope?.id,value.accountScope?.version]);

export function createShortCoachService(transport:Transport,session:()=>Promise<Session>):ShortCoachService{
 async function active(input:CoachInput,signal?:AbortSignal){
  signal?.throwIfAborted();const current=await session();signal?.throwIfAborted();
  if(!current.authenticated||!current.userId||current.accountScope?.id!==input.binding.accountScope.id||current.accountScope?.version!==input.binding.accountScope.version)
   throw new Error('当前客户空间与短句请求不一致。');
  return current;
 }
 async function validate(input:CoachInput,signal?:AbortSignal){
  const current=await active(input,signal);
  if(await textDigest(input.content)!==input.binding.draftHash)throw new Error('草稿已变化，请重新预览。');
  signal?.throwIfAborted();return current;
 }
 async function unchanged(input:CoachInput,before:Session,signal?:AbortSignal){
  if(identity(await active(input,signal))!==identity(before))throw new Error('账户已变化，未采用旧短句结果。');
 }
 return {
  async preview(raw,signal){
   const input=coachInputSchema.parse(raw),before=await validate(input,signal);
   const hash=await coachInputHash(input);await unchanged(input,before,signal);
   const preview=coachPreviewSchema.parse(await transport('shortCoach.preview','/short-coach/preview','POST',input,signal));
   if(preview.inputHash!==hash||preview.policyVersion!==coachPolicy(input))throw new Error('模型预览与当前原文、草稿或资料授权不一致。');
   await unchanged(input,before,signal);return preview;
  },
  async generate(raw,signal){
   const input=coachGenerateSchema.parse(raw),before=await validate(input,signal);
   if(await coachInputHash(input)!==input.disclosure.inputHash)throw new Error('确认内容已变化，请重新预览。');
   await unchanged(input,before,signal);
   const candidate=readCoachSuggestion(await transport('shortCoach.generate','/short-coach/generate','POST',input,signal),input);
   if(Array.from(candidate.content).length>120||(candidate.content.match(/[?？]/g)||[]).length!==1||!/[?？]$/.test(candidate.question))
    throw new Error('建议不是一个简短明确的问题，请保留原稿。');
   await unchanged(input,before,signal);return candidate;
  },
 };
}
