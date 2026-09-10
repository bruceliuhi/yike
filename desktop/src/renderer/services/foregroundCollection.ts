import type {YikeDesktopApi} from '../../shared/contracts';
import {foregroundCollectionCommandSchema, foregroundCollectionResultSchema,
  type ForegroundCollectionCommand, type ForegroundCollectionResult} from '../../shared/foregroundCollection';
import type {PlatformConnection} from '../domain/models';
import {hasForegroundBinding} from '../domain/task';
import {ServiceError} from './contracts';

export interface ForegroundCollectionService {
  execute(command: ForegroundCollectionCommand): Promise<ForegroundCollectionResult>;
}
const cache = new WeakMap<YikeDesktopApi, ForegroundCollectionService>();
export function foregroundCollection(bridge: YikeDesktopApi | undefined): ForegroundCollectionService | undefined {
  if (!bridge || typeof bridge.foregroundCollectionCommand !== 'function') return undefined;
  const known = cache.get(bridge);
  if (known) return known;
  const invoke = bridge.foregroundCollectionCommand.bind(bridge);
  const service = Object.freeze({async execute(input: ForegroundCollectionCommand): Promise<ForegroundCollectionResult> {
    try {
      const command = foregroundCollectionCommandSchema.parse(input);
      const result = foregroundCollectionResultSchema.parse(await invoke(command));
      if (result.state === 'AVAILABLE' && command.action !== 'CAPABILITIES' ||
          result.state === 'STATUS' && (command.action === 'CAPABILITIES' || result.taskId !== command.taskId)) throw new Error();
      return result;
    } catch { throw new ServiceError('FOREGROUND_COLLECTION_RESPONSE_INVALID',
      '采集响应未核实，原批次与请求已保留；请查询状态，不要重新采集。'); }
  }});
  cache.set(bridge, service);
  return service;
}
export function attachForegroundBinding(rows: PlatformConnection[], result: ForegroundCollectionResult): PlatformConnection[] {
  if (result.state !== 'AVAILABLE') return rows;
  const matched=new Map<PlatformConnection,typeof result.bindings[number]>();
  for(const binding of result.bindings){const matching=rows.filter(row=>hasForegroundBinding({...row,foregroundBinding:binding}));
    if(matching.length!==1)return rows;matched.set(matching[0],binding);}
  return rows.map(row=>{const binding=matched.get(row);return binding?{...row,foregroundBinding:binding,capabilities:['search'],
    reason:'本机受控采集支持已核对，仅限当前账号的单次搜索；不代表采集成功。'}:row;});
}
