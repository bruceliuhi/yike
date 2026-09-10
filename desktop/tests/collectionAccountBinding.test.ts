import {expect,it,vi} from 'vitest';
import {resolveCollectionAccount} from '../src/main/collectionAccountBinding';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const account='66c01234abcdef0123456789';
function fixture(){
 let current=true;
 const row={connection_id:id(3),device_id:id(1),account_public_id:account,platform:'XIAOHONGSHU',status:'CONNECTED',connection_version:2,connected_at:'2026-09-10T05:00:00Z',disconnected_at:null};
 const verification={request_id:id(4),action:'VERIFY',device_id:id(1),connection_id:id(3),expected_connection_version:1,platform:'XIAOHONGSHU',account_public_id:account,session_ref:`vault://platform/${id(5)}`};
 const scope={session:{userId:'owner',sessionId:id(2),isCurrent:()=>current},device:{deviceId:id(1),credentialVersion:1},transport:{requestExecution:vi.fn(),requestCandidate:vi.fn(),requestConnection:vi.fn(async(input:any)=>({ok:true,status:200,data:input.operation==='connections.current'?{items:[row]}:{request_id:id(4),device_id:id(1),action:'VERIFY',state:'SUCCEEDED',connection_id:id(3),connection_version:2,connection_status:'CONNECTED',error_code:null}}))},close:vi.fn()};
 const record={version:1,state:'RESOLVED',scope:{serviceOrigin:'https://pilot.example',userId:'owner',deviceId:id(1),platform:'XIAOHONGSHU'},flowId:id(6),profileId:id(5),registration:{...verification,action:'REGISTER',connection_id:null,request_id:id(7),expected_connection_version:0},verification};
 const store={read:vi.fn(async()=>record)};
 const target={platform:'XIAOHONGSHU',access_mode:'PLATFORM_ACCOUNT',connection_id:id(3),connection_version:2};
 return {row,scope,record,store,target,input:{serviceOrigin:'https://pilot.example',scope,store,target} as unknown as Parameters<typeof resolveCollectionAccount>[0],invalidate:()=>current=false};
}
it('resolves only the main protected profile after original VERIFY and exact current connection',async()=>{
 const f=fixture();expect(await resolveCollectionAccount(f.input)).toEqual({profileId:id(5),accountPublicId:account});
 expect(f.store.read).toHaveBeenCalledWith(f.record.scope);expect(f.scope.transport.requestConnection.mock.calls.map(c=>c[0].operation)).toEqual(['connections.receipt','connections.current']);
});
it.each(['status','device_id','connection_version','account_public_id','platform'])('rejects stale or wrong current %s',async field=>{
 const f=fixture();(f.row as any)[field]=field==='connection_version'?3:'changed';await expect(resolveCollectionAccount(f.input)).rejects.toThrow('COLLECTION_ACCOUNT_UNAVAILABLE');
});
it.each(['PENDING','missing_verify','wrong_reference','wrong_device','wrong_scope'])('rejects protected record %s before platform start',async change=>{
 const f=fixture();if(change==='PENDING')f.record.state='PENDING';if(change==='missing_verify')(f.record as any).verification=null;
 if(change==='wrong_reference')f.record.verification.session_ref='vault://platform/other';if(change==='wrong_device')f.record.verification.device_id=id(9);if(change==='wrong_scope')f.record.scope.userId='other';
 await expect(resolveCollectionAccount(f.input)).rejects.toThrow('COLLECTION_ACCOUNT_UNAVAILABLE');
});
it('discards lookup when original client session changes during I/O',async()=>{
 const f=fixture();f.store.read.mockImplementation(async()=>{f.invalidate();return f.record;});await expect(resolveCollectionAccount(f.input)).rejects.toThrow('COLLECTION_ACCOUNT_UNAVAILABLE');expect(f.scope.transport.requestConnection).not.toHaveBeenCalled();
});
