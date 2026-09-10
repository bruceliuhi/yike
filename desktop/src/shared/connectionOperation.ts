import {z} from 'zod';
import {deviceUuidSchema as uuid} from './deviceRegistration';
const version = z.number().int().min(1).max(2147483647);
const text = (max: number) => z.string().min(1).refine(s => Array.from(s).length <= max && s.trim() === s && !/\p{C}/u.test(s));
const publicId = text(256).refine(s => !/(cookie=|token=|password=|secret=|authorization:)/i.test(s));
const reference = text(512).regex(/^vault:\/\/[A-Za-z0-9._~:/-]+$/).refine(s => !/(cookie=|token=|password=|secret=|authorization:)/i.test(s));
const platform = z.enum(['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB']);
export const connectionOperationSchema = z.object({request_id: uuid, action: z.enum(['REGISTER', 'VERIFY', 'DISCONNECT']), device_id: uuid,
  connection_id: uuid.nullable(), expected_connection_version: z.number().int().min(0).max(2147483647), platform: platform.nullable(),
  account_public_id: publicId.nullable(), session_ref: reference.nullable()}).strict().refine(r => r.action === 'DISCONNECT'
    ? r.connection_id !== null && r.expected_connection_version > 0 && r.platform === null && r.account_public_id === null && r.session_ref === null
    : r.platform !== null && r.account_public_id !== null && r.session_ref !== null && (r.action === 'REGISTER'
      ? r.connection_id === null : r.connection_id !== null && r.expected_connection_version > 0));
export type ConnectionOperation = z.infer<typeof connectionOperationSchema>;
const receiptSchema = z.object({request_id: uuid, device_id: uuid, action: z.enum(['REGISTER', 'VERIFY', 'DISCONNECT']),
  state: z.enum(['SUCCEEDED', 'REJECTED']), connection_id: uuid.nullable(), connection_version: version.nullable(),
  connection_status: z.enum(['UNVERIFIED', 'CONNECTED', 'DISCONNECTED', 'EXPIRED']).nullable(),
  error_code: z.enum(['device_unavailable', 'connection_unavailable', 'connection_version_conflict', 'connection_version_exhausted']).nullable()}).strict();
export function parseConnectionReceipt(value: unknown, rawRequest: unknown) {
  const request = connectionOperationSchema.parse(rawRequest), receipt = receiptSchema.parse(value);
  if (receipt.request_id !== request.request_id || receipt.device_id !== request.device_id || receipt.action !== request.action ||
      [receipt.connection_id, receipt.connection_version, receipt.connection_status].some(v => (v === null) !== (receipt.connection_id === null))) throw new Error('INVALID_CONNECTION_RECEIPT');
  if (receipt.state === 'SUCCEEDED') {
    const expectedStatus = {REGISTER: 'UNVERIFIED', VERIFY: 'CONNECTED', DISCONNECT: 'DISCONNECTED'}[request.action];
    if (receipt.error_code !== null || receipt.connection_id === null || receipt.connection_version === null || receipt.connection_status !== expectedStatus ||
        request.connection_id !== null && receipt.connection_id !== request.connection_id ||
        (request.action === 'REGISTER' ? receipt.connection_version !== request.expected_connection_version + 1
          : ![request.expected_connection_version, request.expected_connection_version + 1].includes(receipt.connection_version))) throw new Error('INVALID_CONNECTION_RECEIPT');
  } else if (receipt.error_code === null) throw new Error('INVALID_CONNECTION_RECEIPT');
  return receipt;
}
