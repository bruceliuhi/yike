import {expect,it} from 'vitest';
import {monitorTargets} from '../src/renderer/domain/monitorCollection';

const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
function view(platforms:string[]){return {schema_version:'strategy-confirmation-v1',strategy_version_id:id(2),profile_version_id:id(1),draft_id:id(3),draft_revision:1,
 profile_sha256:'a'.repeat(64),configuration_sha256:'b'.repeat(64),snapshot:{profile_version_id:id(1),strategy_version_id:id(2),platforms,max_records:10,max_runtime_seconds:60,
 configuration:{schema_version:'research-strategy-v1',name:'监控',source:'search',keywords:['AI'],exclusions:[],links:[],mode:'monitor',schedule,research:null,publicSource:'v2ex-latest-v1'}},
 state:'CONFIRMED',created_at:'2026-09-11T00:00:00Z',confirmed_at:'2026-09-11T00:00:00Z',revoked_at:null,is_current:true,profile_current:true} as any;}
const publicRow=(device=id(10),monitorSupported:boolean|undefined=true)=>({platform:'web',accountId:null,accountName:null,status:'CONNECTED',capabilities:['search'],
 publicBinding:{sourceId:'v2ex-latest-v1',deviceId:device,...(monitorSupported?{monitorSupported:true}:{})}} as any);
const nativeRow={platform:'bilibili',accountId:'123456',status:'CONNECTED',capabilities:['search'],registration:{deviceId:id(10),connectionId:id(11),version:1,connectedAt:'2026-09-11T00:00:00Z',disconnectedAt:null},
 foregroundBinding:{mode:'four-platform-foreground-v1',platform:'BILIBILI',connectionId:id(11),connectionVersion:1,deviceId:id(10),accountPublicId:'123456'}} as any;

it('builds anonymous null targets for public-only and same-device mixed monitors',()=>{
 expect(monitorTargets(view(['PUBLIC_WEB']),[publicRow()])).toEqual([{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null}]);
 expect(monitorTargets(view(['BILIBILI','PUBLIC_WEB']),[nativeRow,publicRow()])).toHaveLength(2);
});

it('rejects old public bindings and mixed devices',()=>{
 expect(()=>monitorTargets(view(['PUBLIC_WEB']),[publicRow(id(10),false)])).toThrow('持续监控尚未接通');
 expect(()=>monitorTargets(view(['BILIBILI','PUBLIC_WEB']),[nativeRow,publicRow(id(12))])).toThrow('同一台当前设备');
});
