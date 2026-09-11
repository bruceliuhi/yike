import {z} from 'zod';
import {deviceUuidSchema as uuid} from './deviceRegistration';
import {nativeLoginPlatformSchema,validNativeAccount} from './platformAccount';
export const FOREGROUND_COLLECTION_CHANNEL='desktop:foreground-collection';
export const foregroundCollectionCommandSchema=z.discriminatedUnion('action',[
 z.object({action:z.literal('CAPABILITIES')}).strict(),
 z.object({action:z.literal('STATUS'),taskId:uuid}).strict(),
 z.object({action:z.literal('RECOVER'),taskId:uuid,humanConfirmed:z.literal(true),retry:z.boolean().optional()}).strict(),
]);
export const foregroundModeSchema=z.enum(['xhs-foreground-v1','three-platform-foreground-v1','four-platform-foreground-v1']);
export function supportsForegroundPlatform(mode:unknown,platform:unknown):boolean {
 return nativeLoginPlatformSchema.safeParse(platform).success && (mode==='four-platform-foreground-v1' ||
  mode==='three-platform-foreground-v1' && platform!=='ZHIHU' || mode==='xhs-foreground-v1' && platform==='XIAOHONGSHU');
}
export const monitorSupportSchema=z.object({schema_version:z.literal('monitor-runtime-support-v1'),
 mode:z.enum(['three-platform-monitor-v1','four-platform-monitor-v1']).nullable()}).strict();
export function monitorForegroundMode(value:unknown) {
 const parsed=monitorSupportSchema.safeParse(value);
 return !parsed.success || parsed.data.mode===null ? null : parsed.data.mode==='four-platform-monitor-v1'
  ? 'four-platform-foreground-v1' as const : 'three-platform-foreground-v1' as const;
}
export const foregroundBindingSchema=z.object({mode:foregroundModeSchema,platform:nativeLoginPlatformSchema,
 connectionId:uuid,connectionVersion:z.number().int().min(1).max(2147483647),deviceId:uuid,accountPublicId:z.string().min(1).max(64)}).strict()
 .superRefine((value,ctx)=>{if(!supportsForegroundPlatform(value.mode,value.platform) || !validNativeAccount(value.platform,value.accountPublicId))
  ctx.addIssue({code:'custom',message:'invalid foreground account binding'});});
export const publicSourceBindingSchema=z.object({sourceId:z.literal('v2ex-latest-v1'),deviceId:uuid}).strict();
export type PublicSourceBinding=z.infer<typeof publicSourceBindingSchema>;
const foregroundBindingsSchema=z.array(foregroundBindingSchema).max(4).superRefine((values,ctx)=>{
 if(new Set(values.map(value=>value.platform)).size!==values.length)ctx.addIssue({code:'custom',message:'duplicate foreground platform'});
 if(values.length && new Set(values.map(value=>value.mode)).size!==1)ctx.addIssue({code:'custom',message:'mixed foreground mode'});
});
export const foregroundCollectionResultSchema=z.discriminatedUnion('state',[
 z.object({state:z.literal('AVAILABLE'),bindings:foregroundBindingsSchema,publicBinding:publicSourceBindingSchema.optional()}).strict().superRefine((value,ctx)=>{
  if(!value.bindings.length&&!value.publicBinding)ctx.addIssue({code:'custom',message:'missing collection binding'});
  if(value.publicBinding&&value.bindings.some(binding=>binding.deviceId!==value.publicBinding!.deviceId))
   ctx.addIssue({code:'custom',message:'mixed collection devices'});
 }),
 z.object({state:z.enum(['UNAVAILABLE','BUSY','SESSION_CHANGED','INVALID_REQUEST','NOT_FOUND'])}).strict(),
 z.object({state:z.literal('STATUS'),taskId:uuid,localState:z.enum(['COLLECTING','INTERRUPTED','UPLOAD_UNKNOWN','FINISH_UNKNOWN','COMPLETED','STOPPED','FAILED']),
  serverStatus:z.enum(['PENDING','RUNNING','CANCELLING','CANCELED','SUCCEEDED']),stopConfirmed:z.boolean(),recordsUsed:z.number().int().min(0),recoverable:z.boolean()}).strict(),
]);
export type ForegroundCollectionCommand=z.infer<typeof foregroundCollectionCommandSchema>;
export type ForegroundCollectionResult=z.infer<typeof foregroundCollectionResultSchema>;
export type ForegroundBinding=z.infer<typeof foregroundBindingSchema>;
