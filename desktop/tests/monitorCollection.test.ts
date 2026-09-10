import {describe,expect,it} from 'vitest';
import {monitorCollectionCommandSchema,monitorCollectionResultSchema} from '../src/shared/monitorCollection';

const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const targets=[{platform:'BILIBILI',access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:2}] as const;

describe('native monitor collection contract',()=>{
 it('requires explicit intent and complete binding inputs',()=>{
  expect(monitorCollectionCommandSchema.parse({action:'CREATE',requestId:id(1),profileVersionId:id(2),strategyVersionId:id(3),targets,humanConfirmed:true})).toMatchObject({action:'CREATE'});
  expect(monitorCollectionCommandSchema.parse({action:'ATTACH',planId:id(1),expectedRevision:2,targets,humanConfirmed:true})).toMatchObject({action:'ATTACH'});
  expect(monitorCollectionCommandSchema.parse({action:'SET_STATE',requestId:id(4),planId:id(1),expectedRevision:2,state:'PAUSED',targets,humanConfirmed:true})).toMatchObject({action:'SET_STATE'});
  for(const bad of [
   {action:'CREATE',requestId:id(1),profileVersionId:id(2),strategyVersionId:id(3),targets,humanConfirmed:false},
   {action:'ATTACH',planId:id(1),expectedRevision:true,targets,humanConfirmed:true},
   {action:'SET_STATE',requestId:id(4),planId:id(1),expectedRevision:2,state:'STOPPED',targets,humanConfirmed:true},
  ])expect(monitorCollectionCommandSchema.safeParse(bad).success).toBe(false);
 });

 it('publishes only bounded plan and local runtime state',()=>{
  const plan={planId:id(1),profileVersionId:id(2),strategyVersionId:id(3),configurationSha256:'a'.repeat(64),state:'ACTIVE',revision:2,
   schedule:{kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1},nextDueAt:'2026-09-11T10:00:00Z',
   localState:'ATTACHED',taskId:null,lastError:null};
  expect(monitorCollectionResultSchema.parse({state:'LIST',supported:true,plans:[plan],serverTime:'2026-09-11T09:00:00Z'})).toEqual({state:'LIST',supported:true,plans:[plan],serverTime:'2026-09-11T09:00:00Z'});
  expect(monitorCollectionResultSchema.safeParse({state:'LIST',supported:true,plans:[{...plan,startRequest:{signature:'secret'}}],serverTime:null}).success).toBe(false);
 });
});
