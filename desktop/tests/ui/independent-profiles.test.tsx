// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {AppProvider} from '../../src/renderer/app/context';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
import {ProfilePage} from '../../src/renderer/pages/Profile';
import {service as baseService,profileDescription} from '../../src/renderer/services/client';
import type {Profile} from '../../src/renderer/domain/models';
const a='11111111111111111111111111111111', b='22222222222222222222222222222222';
const id='11111111-1111-4111-8111-111111111111';
const first:Profile={id,profileEntityId:a,version:1,status:'CONFIRMED',description:'test',fields:{service:'软件',customer:'企业',regions:'北京',preference:'',exclusions:''}};
afterEach(()=>{cleanup();clearLocalDrafts();sessionStorage.clear();delete (window as any).yikeDesktop;window.history.replaceState(null,'','/');});
function mount(){
  window.history.replaceState(null,'','#/profile');
  const service={...baseService,session:vi.fn(async()=>({authenticated:true,userId:'multi-profile-test'})),
    profiles:vi.fn(async()=>[{...first,businessName:'软件业务'},{...first,id:'22222222-2222-4222-8222-222222222222',profileEntityId:b,businessName:'教育业务'}]),
    saveProfile:vi.fn().mockRejectedValue(new Error('结果未知')),confirmProfile:vi.fn()};
  render(<AppProvider service={service}><ProfilePage/></AppProvider>);return service;
}
it('edits the selected named business without falling back to the default entity',async()=>{
  const service=mount();await screen.findByRole('option',{name:'软件业务 · 版本 1 · 已确认'});
  fireEvent.change(screen.getByLabelText('服务地区',{selector:'input'}),{target:{value:'上海'}});
  fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
  await waitFor(()=>expect(service.saveProfile).toHaveBeenCalledWith({...first.fields,regions:'上海'},{profileEntityId:a}));
});
it('new business clears old context and retries with the same persisted identity after an unknown result',async()=>{
  const service=mount();await screen.findByDisplayValue('软件');
  fireEvent.click(screen.getByRole('button',{name:'新建业务画像'}));
  expect((screen.getByLabelText('服务内容',{selector:'input'}) as HTMLInputElement).value).toBe('');
  for(const [label,value] of [['业务名称','新业务'],['服务内容','设计'],['目标客户','制造企业'],['服务地区','全国']])
    fireEvent.change(screen.getByLabelText(label,{selector:'input'}),{target:{value}});
  fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
  await waitFor(()=>expect(service.saveProfile).toHaveBeenCalledTimes(1));
  await screen.findByText('结果未知');
  fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
  await waitFor(()=>expect(service.saveProfile).toHaveBeenCalledTimes(2));
  const options=service.saveProfile.mock.calls[0][1];
  expect(options).toEqual({newBusiness:{requestId:expect.any(String),name:'新业务'}});
  expect(service.saveProfile.mock.calls[1][1]).toEqual(options);
  expect(service.confirmProfile).not.toHaveBeenCalled();
});
it('asks before discarding a modified business to start another',async()=>{
  mount();await screen.findByDisplayValue('软件');
  fireEvent.change(screen.getByLabelText('服务内容',{selector:'input'}),{target:{value:'未保存业务'}});
  fireEvent.click(screen.getByRole('button',{name:'新建业务画像'}));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'取消'}));
  expect((screen.getByLabelText('服务内容',{selector:'input'}) as HTMLInputElement).value).toBe('未保存业务');
});
it('ordinary adapter carries entity selection and rejects incoherent explicit receipts',async()=>{
  const requestApi=vi.fn().mockResolvedValue({ok:true,status:200,data:{version_id:id,profile_id:a,profile_name:'软件业务',version:2,status:'DRAFT'}});
  (window as any).yikeDesktop={requestApi};
  const saved=await baseService.saveProfile(first.fields,{profileEntityId:a} as any);
  expect(saved).toMatchObject({profileEntityId:a,businessName:'软件业务'});
  expect(requestApi).toHaveBeenCalledWith({operation:'profiles.save',payload:{description:profileDescription(first.fields),profileEntityId:a}});
  await expect(baseService.saveProfile(first.fields,{profileEntityId:b} as any)).rejects.toBeDefined();
  const calls=requestApi.mock.calls.length;
  await expect(baseService.saveProfile(first.fields,{profileEntityId:a,newBusiness:{requestId:id,name:'冲突'}} as any)).rejects.toBeDefined();
  expect(requestApi).toHaveBeenCalledTimes(calls);
});
