// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {AppProvider,useApp} from '../../src/renderer/app/context';
import {SettingsPage} from '../../src/renderer/pages/Settings';
import {CustomerDataActions} from '../../src/renderer/pages/settings/ManagementActions';
import {service as base} from '../../src/renderer/services/client';
import {unavailableManagement,type ManagementService} from '../../src/renderer/services/management';
import {downloadText} from '../../src/renderer/services/download';
import type {Session} from '../../src/renderer/domain/models';

vi.mock('../../src/renderer/services/download',()=>({downloadText:vi.fn(),downloadErrorMessage:()=> '文件保存失败'}));
beforeEach(()=>{localStorage.clear();vi.mocked(downloadText).mockReset().mockResolvedValue({status:'saved'});});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();localStorage.clear();});
const accountScope={id:'TEST-shared-space',version:1};
const sessionA:Session={authenticated:true,userId:'TEST-user-a',accountScope};
const account={userId:'TEST-user-a',accountScope,spaceId:accountScope.id,spaceName:'TEST-A空间',revision:'r1',
  license:{status:'ACTIVE' as const,expiresAt:null},device:null};
const receipt={userId:account.userId,accountScope,spaceId:account.spaceId,name:'商机.csv',content:'标题\r\nA商机\r\n'};
const identityError='账号或客户空间已变化，请重新登录；没有采用返回的账号信息或导出文件。';
function SessionControls(){
  const {session,refreshSession}=useApp();
  return <><span>{session.userId}:{session.accountScope?.id}:{session.accountScope?.version}</span>
    <button onClick={()=>void refreshSession()}>刷新测试身份</button></>;
}
function mount(overrides:Partial<ManagementService>,settings=false,initialSession=sessionA){
  let nextSession=initialSession;
  const service={...base,management:{...unavailableManagement,...overrides},
    session:vi.fn(async()=>nextSession),
    info:vi.fn(async()=>({version:'TEST',platform:'darwin',serviceConfigured:true}))};
  render(<AppProvider service={service}><SessionControls />{settings?<SettingsPage />:
    <CustomerDataActions account={account} backup={false} changed={()=>{}} />}</AppProvider>);
  return async(value:Session)=>{
    nextSession=value;
    fireEvent.click(screen.getByRole('button',{name:'刷新测试身份'}));
    await screen.findByText(`${value.userId}:${value.accountScope?.id}:${value.accountScope?.version}`);
  };
}
async function ready(){await screen.findByText('TEST-user-a:TEST-shared-space:1');}
it('does not adopt same-tenant user B account returned while the UI still holds session A',async()=>{
  mount({account:vi.fn(async()=>({...account,userId:'TEST-user-b',spaceName:'TEST-B私有名称'}))},true);
  await ready();
  await screen.findByText(identityError);
  expect(screen.queryByText('已激活')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'导出数据'}));
  expect(screen.queryByText(/TEST-B私有名称/)).toBeNull();
  expect(downloadText).not.toHaveBeenCalled();
});
it.each(['user','scope','version','missing'] as const)('rejects an export with mismatched %s without saving or success toast',async(kind)=>{
  const result={...receipt,...(kind==='user'?{userId:'TEST-user-b'}:
    kind==='scope'?{accountScope:{id:'TEST-other-space',version:1}}:
    kind==='version'?{accountScope:{...accountScope,version:2}}:{userId:undefined})};
  mount({exportData:vi.fn().mockResolvedValue(result)});
  await ready();
  fireEvent.click(screen.getByRole('button',{name:'生成并保存 CSV'}));
  await screen.findByText(identityError);
  expect(downloadText).not.toHaveBeenCalled();
  expect(screen.queryByText('客户数据导出文件已保存。')).toBeNull();
});
it.each(['id','version'] as const)('discards an old export when only authenticated accountScope.%s changes',async(field)=>{
  let resolve!:(value:typeof receipt)=>void;
  const exporting=vi.fn(()=>new Promise<typeof receipt>(done=>{resolve=done;}));
  const changeSession=mount({exportData:exporting});
  await ready();
  fireEvent.click(screen.getByRole('button',{name:'生成并保存 CSV'}));
  await waitFor(()=>expect(exporting).toHaveBeenCalledTimes(1));
  await changeSession({...sessionA,accountScope:field==='id'?{id:'TEST-other-space',version:1}:{...accountScope,version:2}});
  await act(async()=>resolve(receipt));
  expect(downloadText).not.toHaveBeenCalled();
  expect(screen.queryByText('客户数据导出文件已保存。')).toBeNull();
});
it('does not announce a late saved receipt after authenticated scope version changes',async()=>{
  let resolve!:(value:{status:'saved'})=>void;
  vi.mocked(downloadText).mockImplementation(()=>new Promise(done=>{resolve=done;}));
  const changeSession=mount({exportData:vi.fn().mockResolvedValue(receipt)});
  await ready();
  fireEvent.click(screen.getByRole('button',{name:'生成并保存 CSV'}));
  await waitFor(()=>expect(downloadText).toHaveBeenCalledTimes(1));
  await changeSession({...sessionA,accountScope:{...accountScope,version:2}});
  await act(async()=>resolve({status:'saved'}));
  expect(screen.queryByText('客户数据导出文件已保存。')).toBeNull();
});
it('rejects a same-tenant cookie identity switch through the production browser adapter',async()=>{
  const scope={id:'11111111-1111-4111-8111-111111111111',version:1};
  const owner='22222222-2222-4222-8222-222222222222';
  let cookieUser=owner;
  const fetcher=vi.fn(async(path:RequestInfo|URL)=>Response.json(
    String(path).endsWith('/management/account')
      ?{...account,userId:cookieUser,spaceId:scope.id,accountScope:scope}
      :{...receipt,userId:cookieUser,spaceId:scope.id,accountScope:scope}));
  vi.stubGlobal('fetch',fetcher);
  mount({...base.management!},true,{authenticated:true,userId:owner,accountScope:scope});
  await screen.findByText('已激活');
  cookieUser='33333333-3333-4333-8333-333333333333';
  fireEvent.click(screen.getByRole('button',{name:'导出数据'}));
  fireEvent.click(screen.getByRole('button',{name:'生成并保存 CSV'}));
  await screen.findByText(identityError);
  expect(fetcher).toHaveBeenCalledWith('/api/ui/management/export?kind=csv',expect.objectContaining({credentials:'same-origin'}));
  expect(downloadText).not.toHaveBeenCalled();
  expect(screen.queryByText('客户数据导出文件已保存。')).toBeNull();
});
