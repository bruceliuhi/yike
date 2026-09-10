import {createHash} from 'node:crypto';
import {z} from 'zod';
import type {DeviceKeyMaterial} from './deviceKeyVault';
import {canonicalJson,signCanonicalOutreachPayload} from './outreachDispatchSigner';
import {outreachConfirmationSchema,type OutreachConfirmation} from './outreachConfirmationProtocol';
const sha=z.string().regex(/^[a-f0-9]{64}$/),uuid=z.string().uuid();
const preparedSchema=z.object({signing_payload:z.string().min(2).max(16384),requestId:uuid,requestSha256:sha}).strict();
const payloadSchema=z.object({protocol:z.literal('yike-outreach-confirmation-v1'),tenant_id:uuid,user_id:uuid,
  session_digest:sha,request:outreachConfirmationSchema}).strict();
export function signOutreachConfirmation(input:{key:DeviceKeyMaterial;prepared:unknown;expected:{serviceOrigin:string;userId:string;tenantId:string;request:OutreachConfirmation}}) {
  try {
    const request=outreachConfirmationSchema.parse(input.expected.request),prepared=preparedSchema.parse(input.prepared);
    const p=payloadSchema.parse(JSON.parse(prepared.signing_payload));
    if(Buffer.byteLength(prepared.signing_payload,'utf8')>16384 || canonicalJson(p)!==prepared.signing_payload ||
      p.tenant_id!==input.expected.tenantId || p.user_id!==input.expected.userId || canonicalJson(p.request)!==canonicalJson(request) ||
      prepared.requestId!==request.requestId || prepared.requestSha256!==createHash('sha256').update(canonicalJson(request)).digest('hex'))throw Error();
    return {request,signature:signCanonicalOutreachPayload(input.key,{...input.expected,deviceId:request.context.deviceId},prepared.signing_payload)};
  }catch{throw new Error('OUTREACH_CONFIRMATION_SIGNING_FAILED');}
}
