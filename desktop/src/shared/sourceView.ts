import {z} from 'zod';
export const SOURCE_VIEW_CHANNEL='desktop:source-view';
export const sourceViewResultSchema=z.union([
  z.object({state:z.literal('OPENED'),sourceKind:z.enum(['POST','COMMENT'])}).strict(),
  z.object({state:z.literal('BUSY')}).strict(),
  z.object({state:z.literal('FAILED'),error:z.enum(['SOURCE_VIEW_UNAVAILABLE','SOURCE_STOP_FAILED'])}).strict(),
]);
export type SourceViewResult=z.infer<typeof sourceViewResultSchema>;
