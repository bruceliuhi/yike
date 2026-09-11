// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {AppProvider} from '../../src/renderer/app/context';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
import {ProfilePage} from '../../src/renderer/pages/Profile';
import {service as baseService} from '../../src/renderer/services/client';
import type {Profile} from '../../src/renderer/domain/models';
const id='11111111-1111-4111-8111-111111111111', ref='22222222-2222-4222-8222-222222222222';
const profile:Profile={id,version:1,status:'CONFIRMED',description:'TEST',fields:{service:'服务A',customer:'企业',regions:'上海',preference:'',exclusions:''},materialReferences:[{field:'service',referenceId:ref,valid:false}]};
afterEach(()=>{cleanup();clearLocalDrafts();sessionStorage.clear();window.history.replaceState(null,'','/');});
function mount(value=profile,materials?:any){
  const service={...baseService,session:vi.fn(async()=>({authenticated:true,userId:'reference-test'})),profiles:vi.fn(async()=>[value]),
    saveProfile:vi.fn(async(fields:any,options:any)=>({...value,version:2,status:'DRAFT' as const,fields,materialReferences:options?.materialReferences?.length?[{field:'service' as const,referenceId:ref,valid:true}]:[]})),confirmProfile:vi.fn(),materials};
  render(<AppProvider service={service}><ProfilePage/></AppProvider>);return service;
}
it('shows invalid provenance and allows explicit manual detachment without erasing text',async()=>{
  window.history.replaceState(null,'','#/profile');const service=mount();
  await screen.findByText('服务内容：资料引用已失效，请重新采用有效资料或改为人工内容。');
  fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));expect(service.saveProfile).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'服务内容改为人工内容'}));
  expect((screen.getByLabelText('服务内容',{selector:'input'}) as HTMLInputElement).value).toBe('服务A');
  fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
  await waitFor(()=>expect(service.saveProfile).toHaveBeenCalledWith(profile.fields,{baseProfileVersionId:id,materialReferences:[]}));
  expect(service.confirmProfile).not.toHaveBeenCalled();
});
it('preserves unedited inherited fields when another profile field changes',async()=>{
  window.history.replaceState(null,'','#/profile');const service=mount({...profile,materialReferences:[{field:'service',referenceId:ref,valid:true}]});
  await screen.findByText('服务内容：已记录资料引用。');
  fireEvent.change(screen.getByLabelText('服务地区',{selector:'input'}),{target:{value:'北京'}});
  fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
  await waitFor(()=>expect(service.saveProfile).toHaveBeenCalledWith({...profile.fields,regions:'北京'},{baseProfileVersionId:id,materialReferences:[{field:'service',referenceId:ref}]}));
});
it('passes the selected material identity through the existing apply then save flow',async()=>{
  window.history.replaceState(null,'','#/profile?tab=materials');
  const material={id:'m-one',version:4,profileVersionId:id,name:'TEST 资料',text:'服务B',purpose:'产品介绍',visibility:'internal',status:'READY',updatedAt:'2026-09-11T00:00:00Z',extraction:{id:'e-one',materialVersion:4,fields:{service:'服务B'},evidence:[{field:'service',quote:'服务B'}]}};
  const service=mount({...profile,materialReferences:[]},{list:vi.fn(async()=>[material])});
  fireEvent.click(await screen.findByRole('button',{name:'用于画像'}));
  fireEvent.click(screen.getByLabelText('已核对当前画像，确认替换所选字段'));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'填入画像草稿'}));
  fireEvent.click(screen.getByRole('tab',{name:'业务描述'}));
  fireEvent.click(within(await screen.findByRole('dialog',{name:'离开当前页面？'})).getByRole('button',{name:'继续离开'}));
  fireEvent.click(await screen.findByRole('button',{name:'保存草稿'}));
  await waitFor(()=>expect(service.saveProfile).toHaveBeenCalledWith({...profile.fields,service:'服务B'},{materialReferences:[{field:'service',sourceProfileVersionId:id,materialId:'m-one',materialVersion:4,extractionId:'e-one'}]}));
});
