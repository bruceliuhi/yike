// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {service} from '../../src/renderer/services/client';
import {validatedOperation} from '../../src/main/servicePolicy';
import type {YikeDesktopApi} from '../../src/shared/contracts';

const spaceId='11111111-1111-4111-8111-111111111111';
const binding={userId:'22222222-2222-4222-8222-222222222222',accountScope:{id:spaceId,version:1}};
const account={...binding,spaceId,spaceName:'当前客户空间',revision:'a'.repeat(64),
  license:{status:'UNKNOWN',expiresAt:null},device:null};
const host=window as unknown as {yikeDesktop?:YikeDesktopApi};
afterEach(()=>{delete host.yikeDesktop;vi.unstubAllGlobals();});

describe('production read-only management adapter',()=>{
  it('is installed and accepts explicitly unknown commercial device and license',async()=>{
    const requestApi=vi.fn().mockResolvedValue({ok:true,status:200,data:account});
    host.yikeDesktop={requestApi} as unknown as YikeDesktopApi;
    expect(service.management).toBeDefined();
    expect(await service.management!.account()).toEqual(account);
    expect(requestApi).toHaveBeenCalledWith({operation:'management.account'});
  });
  it('uses only fixed GET routes and rejects tenant/owner/kind override',()=>{
    expect(validatedOperation({operation:'management.account'})).toEqual({path:'/api/ui/management/account',method:'GET',logout:false});
    expect(validatedOperation({operation:'management.exportCsv'})).toEqual({path:'/api/ui/management/export?kind=csv',method:'GET',logout:false});
    for(const operation of ['management.account','management.exportCsv']){
      for(const payload of [{tenant_id:spaceId},{owner:'other'},{kind:'backup-json'}]){
        expect(validatedOperation({operation,payload})).toBeNull();
      }
    }
  });
  it('exports a checked CSV receipt and leaves unsupported operations unavailable without dispatch',async()=>{
    const result={...binding,spaceId,name:'意客AI-客户商机.csv',content:'商机标题\r\n真实标题\r\n'};
    const requestApi=vi.fn().mockResolvedValue({ok:true,status:200,data:result});
    host.yikeDesktop={requestApi} as unknown as YikeDesktopApi;
    expect(service.management).toBeDefined();
    expect(await service.management!.exportData('csv')).toEqual(result);
    await expect(service.management!.exportData('backup-json')).rejects.toMatchObject({status:501});
    await expect(service.management!.updates()).rejects.toMatchObject({status:501});
    await expect(service.management!.operation('old-request')).rejects.toMatchObject({status:501});
    expect(requestApi).toHaveBeenCalledExactlyOnceWith({operation:'management.exportCsv'});
  });
  it('rejects malformed/over-limit receipts instead of passing them to saving',async()=>{
    const requestApi=vi.fn();host.yikeDesktop={requestApi} as unknown as YikeDesktopApi;
    expect(service.management).toBeDefined();
    for(const data of [{spaceId,name:'../private.csv',content:'data'},
      {spaceId,name:'ok.csv',content:'x'.repeat(2097153)},
      {spaceId,name:'ok.csv',content:'data',privateKey:'not-exportable'},
      {spaceId:'',name:'ok.csv',content:'data'}]){
      requestApi.mockResolvedValue({ok:true,status:200,data:{...binding,...data}});
      await expect(service.management!.exportData('csv')).rejects.toMatchObject({code:'INVALID_SERVICE_RESPONSE'});
    }
  });
  it('reports an explicit limit error without implying a partial export was complete',async()=>{
    host.yikeDesktop={requestApi:vi.fn().mockResolvedValue({ok:false,status:413,
      error:{detail:{code:'management_export_too_large'}}})} as unknown as YikeDesktopApi;
    await expect(service.management!.exportData('csv')).rejects.toMatchObject({status:413,
      message:'导出超过 1000 条或 2 MiB 上限，未生成部分文件。请在商机库筛选、勾选记录，使用“导出所选客户商机”。'});
  });
  it('requires authoritative owner and scope metadata for both read receipts',async()=>{
    const requestApi=vi.fn();host.yikeDesktop={requestApi} as unknown as YikeDesktopApi;
    for(const field of ['userId','accountScope']){
      const missingAccount={...account,[field]:undefined};
      requestApi.mockResolvedValue({ok:true,status:200,data:missingAccount});
      await expect(service.management!.account()).rejects.toMatchObject({code:'INVALID_SERVICE_RESPONSE'});
      requestApi.mockResolvedValue({ok:true,status:200,data:{...binding,spaceId,name:'ok.csv',content:'ok',[field]:undefined}});
      await expect(service.management!.exportData('csv')).rejects.toMatchObject({code:'INVALID_SERVICE_RESPONSE'});
    }
  });
});
