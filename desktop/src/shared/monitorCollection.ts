import {z} from 'zod';
import {deviceUuidSchema as uuid} from './deviceRegistration';
import {executionOperationSchema} from './executionOperation';

export const MONITOR_COLLECTION_CHANNEL='desktop:monitor-collection';
const targets=executionOperationSchema.shape.targets.unwrap().unwrap();
const confirmed=z.literal(true);
const revision=z.number().int().min(1).max(2_147_483_647);
const hhmm=z.string().regex(/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/);
export const monitorScheduleSchema=z.object({kind:z.enum(['daily','interval']),times:z.array(hhmm).max(24),interval:z.number().min(1).max(168),
 start:hhmm,end:hhmm,timezone:z.string().min(1).max(128),policyVersion:z.literal(1)}).strict();

export const monitorCollectionCommandSchema=z.discriminatedUnion('action',[
 z.object({action:z.literal('LIST')}).strict(),
 z.object({action:z.literal('CREATE'),requestId:uuid,profileVersionId:uuid,strategyVersionId:uuid,targets,humanConfirmed:confirmed}).strict(),
 z.object({action:z.literal('ATTACH'),planId:uuid,expectedRevision:revision,targets,humanConfirmed:confirmed}).strict(),
 z.object({action:z.literal('SET_STATE'),requestId:uuid,planId:uuid,expectedRevision:revision,state:z.enum(['ACTIVE','PAUSED']),targets:targets.optional(),humanConfirmed:confirmed}).strict(),
 z.object({action:z.literal('RECEIPT'),command:z.union([
  z.object({action:z.literal('CREATE'),requestId:uuid,profileVersionId:uuid,strategyVersionId:uuid,targets,humanConfirmed:confirmed}).strict(),
  z.object({action:z.literal('SET_STATE'),requestId:uuid,planId:uuid,expectedRevision:revision,state:z.enum(['ACTIVE','PAUSED']),targets:targets.optional(),humanConfirmed:confirmed}).strict(),
 ])}).strict(),
]);

const publicPlan=z.object({
 planId:uuid,profileVersionId:uuid,strategyVersionId:uuid,
 configurationSha256:z.string().length(64).regex(/^[0-9a-f]{64}$/),state:z.enum(['ACTIVE','PAUSED']),revision,
 schedule:monitorScheduleSchema,
 nextDueAt:z.string().datetime({offset:true}).nullable(),
 localState:z.enum(['DETACHED','ATTACHED','RUNNING','STOPPING','STOP_UNCONFIRMED']),
 taskId:uuid.nullable(),lastError:z.string().regex(/^[A-Z][A-Z0-9_]{0,79}$/).nullable(),
}).strict();
export const monitorCollectionResultSchema=z.discriminatedUnion('state',[
 z.object({state:z.literal('LIST'),supported:z.boolean(),plans:z.array(publicPlan).max(20),serverTime:z.string().datetime({offset:true}).nullable()}).strict(),
 z.object({state:z.literal('RECORDED'),requestId:uuid,plan:publicPlan}).strict(),
 z.object({state:z.literal('ATTACHED'),plan:publicPlan}).strict(),
 z.object({state:z.literal('UNKNOWN'),requestId:uuid}).strict(),
 z.object({state:z.enum(['SESSION_CHANGED','BUSY','NOT_FOUND','SIGNED_OUT','DEVICE_NOT_READY','INVALID_REQUEST','SERVICE_UNAVAILABLE','CONFLICT','UNAVAILABLE'])}).strict(),
]);

export type MonitorCollectionCommand=z.infer<typeof monitorCollectionCommandSchema>;
export type MonitorCollectionResult=z.infer<typeof monitorCollectionResultSchema>;
export type MonitorCollectionPlan=z.infer<typeof publicPlan>;

export const MONITOR_COLLECTION_ERROR_MESSAGES={SESSION_CHANGED:'登录会话已变化，请重新确认本机账号。',BUSY:'本机采集槽正在使用，本轮不会重复启动。',
 NOT_FOUND:'未找到原计划或原请求。',SIGNED_OUT:'当前未登录。',DEVICE_NOT_READY:'本机设备尚未就绪。',INVALID_REQUEST:'监控请求无效。',
 SERVICE_UNAVAILABLE:'监控服务暂时不可用。',CONFLICT:'计划版本或账号绑定已变化。',UNAVAILABLE:'当前服务未启用持续监控。'} as const;
