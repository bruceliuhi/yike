import {z} from 'zod';
import type {DeviceKeyMaterial} from './deviceKeyVault';
import {canonicalJson,signCanonicalOutreachPayload} from './outreachDispatchSigner';
import {nativeReplyRequestSchema,type NativeReplyRequest} from './nativeReplyProtocol';

const identity=z.string().uuid().regex(/^[a-f0-9-]+$/),limit=262144;
const expectedSchema=z.object({userId:identity,tenantId:identity,request:nativeReplyRequestSchema,
  serviceOrigin:z.string().max(2048).refine(value=>{
    try{const u=new URL(value);return u.origin===value&&!u.username&&!u.password&&
      (u.protocol==='https:'||u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname));}catch{return false;}
  }),
}).strict();
const payloadSchema=z.object({protocol:z.literal('yike-platform-reply-v1'),user_id:identity,tenant_id:identity,
  session_digest:z.string().regex(/^[a-f0-9]{64}$/),request:nativeReplyRequestSchema}).strict();

export function signNativeReply(input:{key:DeviceKeyMaterial;prepared:unknown;expected:{serviceOrigin:string;userId:string;tenantId:string;request:NativeReplyRequest}}):{request:NativeReplyRequest;signature:string}{
  try{
    const expected=expectedSchema.parse(input.expected);
    const {signing_payload:wire}=z.object({signing_payload:z.string().min(2).max(limit)}).strict().parse(input.prepared);
    if(Buffer.byteLength(wire,'utf8')>limit)throw new Error();
    const payload=payloadSchema.parse(JSON.parse(wire)),event=payload.request.event;
    if(canonicalJson(payload)!==wire||payload.user_id!==expected.userId||payload.tenant_id!==expected.tenantId||
      event.user_id!==expected.userId||event.tenant_id!==expected.tenantId||canonicalJson(payload.request)!==canonicalJson(expected.request))throw new Error();
    return {request:expected.request,signature:signCanonicalOutreachPayload(input.key,
      {...expected,deviceId:expected.request.deviceId},wire)};
  }catch{throw new Error('REPLY_SIGNING_FAILED');}
}
