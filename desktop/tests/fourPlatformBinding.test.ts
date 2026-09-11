import {expect,it} from 'vitest';
import {nativeLoginPlatformSchema,validNativeAccount} from '../src/shared/platformAccount';
import {foregroundBindingSchema,foregroundCollectionResultSchema} from '../src/shared/foregroundCollection';
import {hasForegroundBinding} from '../src/renderer/domain/task';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const binding={mode:'four-platform-foreground-v1',platform:'ZHIHU',connectionId:id(1),connectionVersion:1,deviceId:id(2),accountPublicId:'123456'};
it('requires explicit four-platform mode and an ASCII public uid for Zhihu',()=>{
 expect(nativeLoginPlatformSchema.safeParse('ZHIHU').success).toBe(true);
 expect(foregroundBindingSchema.safeParse(binding).success).toBe(true);
 expect(foregroundBindingSchema.safeParse({...binding,mode:'three-platform-foreground-v1'}).success).toBe(false);
 for(const uid of ['0123','１２３','hash_id','', '1'.repeat(21)])expect(validNativeAccount('ZHIHU',uid)).toBe(false);
 expect(hasForegroundBinding({platform:'zhihu',accountId:'123456',status:'CONNECTED',foregroundBinding:binding,
  registration:{connectionId:id(1),version:1,deviceId:id(2),disconnectedAt:null}} as any)).toBe(true);
});
it('accepts four distinct bindings but rejects duplicate and mixed modes',()=>{
 const bindings=['XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU'].map((platform,index)=>({...binding,platform,connectionId:id(index+3),accountPublicId:platform==='XIAOHONGSHU'?'abcdefgh':'123456'}));
 expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings}).success).toBe(true);
 expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[...bindings,binding]}).success).toBe(false);
 expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[{...bindings[0],mode:'three-platform-foreground-v1'},bindings[3]]}).success).toBe(false);
});
