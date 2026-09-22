import {z} from 'zod';
import type {ApiOperation} from '../../shared/contracts';
import {validatedExport} from '../../shared/exportValidation';
import {accountSchema,managementIdentitySchema} from '../domain/management';
import {ServiceError} from './contracts';
import {unavailableManagement, type ManagementService} from './management';

type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown)=>Promise<unknown>;
const exportSchema=managementIdentitySchema.extend({spaceId:z.string().uuid(),name:z.string(),content:z.string()}).strict();
const invalid=()=>new ServiceError('INVALID_SERVICE_RESPONSE','账号或导出响应不完整，请重新读取；没有保存文件。');

/** Only these two reads are connected. Existing mutation gates remain closed. */
export function createManagementReadService(transport:Transport):ManagementService{
  return {
    ...unavailableManagement,
    async account(){
      const result=accountSchema.strict().safeParse(await transport('management.account','/management/account'));
      if(!result.success)throw invalid();
      return result.data;
    },
    async exportData(kind){
      if(kind!=='csv')return unavailableManagement.exportData(kind);
      const parsed=exportSchema.safeParse(await transport('management.exportCsv','/management/export?kind=csv'));
      if(!parsed.success||!validatedExport({format:'csv',name:parsed.data.name,content:parsed.data.content}))throw invalid();
      return parsed.data;
    },
  };
}
