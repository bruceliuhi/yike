import type { z } from 'zod';
import type { ApiOperation } from '../../shared/contracts';
import {
  suggestionPreviewRequestSchema,suggestionPreviewSchema,suggestionRequestSchema,suggestionReceiptSchema,
  type SuggestionRequest,type SuggestionPreview,type SuggestionReceipt,
} from '../../shared/searchSuggestions';
import { ServiceError } from './contracts';

export interface SearchSuggestionsService {
  preview(profileVersionId:string,signal?:AbortSignal):Promise<SuggestionPreview>;
  submit(request:SuggestionRequest,signal?:AbortSignal):Promise<SuggestionReceipt>;
  getReceipt(request:SuggestionRequest,signal?:AbortSignal):Promise<SuggestionReceipt>;
}
type Transport = (operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
function checked<T>(schema:z.ZodType<T>,value:unknown):T {
  const result=schema.safeParse(value);
  if(!result.success) throw new ServiceError('INVALID_SUGGESTION','搜索建议数据不完整，请核对原请求。');
  return result.data;
}
function receipt(raw:unknown,request:SuggestionRequest):SuggestionReceipt {
  const value=checked(suggestionReceiptSchema,raw);
  if(value.request_id!==request.request_id||value.draft_id!==request.draft_id||
      value.draft_revision!==request.draft_revision||value.profile_version_id!==request.profile_version_id||
      value.profile_sha256!==request.disclosure.profile_sha256||value.model_provider!==request.disclosure.model_provider||
      value.model_name!==request.disclosure.model_name||value.disclosure_policy_version!==request.disclosure.policy_version)
    throw new ServiceError('SUGGESTION_BINDING_MISMATCH','搜索建议回执与原请求不一致，请核对原请求。');
  return value;
}

/** Every operation is explicit. A timeout never retries POST or invents a new request. */
export function createSearchSuggestionsService(transport:Transport):SearchSuggestionsService {
  return {
    async preview(profileVersionId,signal){
      signal?.throwIfAborted();
      const input=checked(suggestionPreviewRequestSchema,{profile_version_id:profileVersionId});
      const value=checked(suggestionPreviewSchema,await transport('suggestions.preview',
        `/search-suggestions/preview?profileVersionId=${input.profile_version_id}`,'GET',input,signal));
      if(value.profile_version_id!==input.profile_version_id)
        throw new ServiceError('SUGGESTION_BINDING_MISMATCH','建议预览与当前画像不一致。');
      return value;
    },
    async submit(input,signal){
      signal?.throwIfAborted();
      const request=checked(suggestionRequestSchema,input);
      return receipt(await transport('suggestions.submit','/search-suggestions','POST',request,signal),request);
    },
    async getReceipt(input,signal){
      signal?.throwIfAborted();
      const request=checked(suggestionRequestSchema,input);
      return receipt(await transport('suggestions.receipt',`/search-suggestions/${request.request_id}`,'GET',
        {request_id:request.request_id},signal),request);
    },
  };
}
