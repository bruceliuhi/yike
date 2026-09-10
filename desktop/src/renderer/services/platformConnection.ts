import type {YikeDesktopApi} from '../../shared/contracts';
import {platformConnectionResultSchema, type PlatformConnectionCommand,
  type PlatformConnectionResult} from '../../shared/platformConnection';
import type {PlatformConnection} from '../domain/models';
import {decodeConnectionRegistry} from './connectionRegistry';
import {ServiceError} from './contracts';

type Bridge = Pick<YikeDesktopApi, 'platformConnectionCommand'>;
type Invoke = (command: PlatformConnectionCommand) => Promise<PlatformConnectionResult>;
type Flow = {id: string; invoke: Invoke};
const cancelled = () => new DOMException('平台连接等待已取消。', 'AbortError');
const unavailable = () => new ServiceError('SERVICE_UNAVAILABLE', '本机平台登录尚未配置或暂不可用，请检查客户端与设备状态。');
function failure(result: PlatformConnectionResult): ServiceError {
  const code = result.state === 'FAILED' ? result.error : result.state;
  const messages: Record<string, string> = {
    WAITING_LOGIN: '登录尚未完成，请在平台原生窗口处理后再次检查。',
    OPENED: '登录尚未完成，请在平台原生窗口处理后再次检查。',
    UNKNOWN: '连接结果尚未确认，请再次检查原请求，不要重复打开登录。',
    CANCELLED: '本次平台登录已取消，请重新打开登录窗口。',
    SESSION_CHANGED: '客户账号已变化，请在当前账号下重新连接。',
    SIGNED_OUT: '请先登录客户空间，再连接平台账号。',
    DEVICE_NOT_READY: '设备尚未就绪，请先在设备与使用授权中完成检查。',
    BUSY: '原登录流程仍在运行或清理，请稍后再试。',
    LOGIN_EXPIRED: '登录等待已过期，请重新打开平台登录窗口。',
    ACCOUNT_MISMATCH: '平台账号与原连接不一致，未变更连接记录。',
    CURRENT_CONNECTION_CHANGED: '当前连接记录已变化，请刷新后核对。',
    SOURCE_STOP_FAILED: '登录窗口停止尚未确认，请核对原生窗口后再试。',
    SERVICE_UNAVAILABLE: unavailable().message,
  };
  return new ServiceError(code, messages[code] || '平台连接未完成，请核对后重试。');
}

/** Main owns every identity/path. Renderer retains only a cancellable opaque flow. */
export function createPlatformConnectionService(
  bridge: () => Bridge | undefined,
  readConnections: () => Promise<PlatformConnection[]>,
) {
  let generation = 0;
  let active: Flow | null = null;
  function invokeForCurrentBridge(): Invoke {
    const owner = bridge();
    if (!owner?.platformConnectionCommand) throw unavailable();
    return async command => {
      let raw: unknown;
      try {raw = await owner.platformConnectionCommand!(command);}
      catch {throw unavailable();}
      const parsed = platformConnectionResultSchema.safeParse(raw);
      if (!parsed.success) throw new ServiceError('INVALID_SERVICE_RESPONSE', '连接响应尚未确认，请核对当前窗口后重试。');
      return parsed.data;
    };
  }
  async function cancelFlow(flow: Flow): Promise<void> {
    const result = await flow.invoke({action: 'CANCEL', platform: 'XIAOHONGSHU', flowId: flow.id});
    if (result.state === 'CANCELLED' && result.flowId === flow.id) return;
    if (result.state === 'SESSION_CHANGED' || result.state === 'SIGNED_OUT') return;
    throw failure(result);
  }
  return {
    async connect(platform: string, signal?: AbortSignal): Promise<void> {
      if (platform !== 'xhs') throw new ServiceError('CAPABILITY_UNAVAILABLE', '该平台登录尚未接通，当前未创建连接。');
      signal?.throwIfAborted();
      const request = ++generation;
      const previous = active;
      active = null;
      let aborted = false;
      const abort = () => {aborted = true;};
      signal?.addEventListener('abort', abort, {once: true});
      const current = () => !aborted && request === generation;
      try {
        if (previous) await cancelFlow(previous);
        if (!current()) throw cancelled();
        const invoke = invokeForCurrentBridge();
        const result = await invoke({action: 'OPEN', platform: 'XIAOHONGSHU'});
        if (!current()) {
          if ('flowId' in result) {
            // A late OPEN belongs to its original bridge/flow, never the newer flow.
            await cancelFlow({id: result.flowId, invoke}).catch(() => {});
          }
          throw cancelled();
        }
        if (result.state !== 'OPENED' && result.state !== 'WAITING_LOGIN' && result.state !== 'UNKNOWN')
          throw failure(result);
        active = {id: result.flowId, invoke};
        if (result.state !== 'OPENED') throw failure(result);
      } finally {
        // UI aborts its previous request before CHECK. An already-opened flow is
        // cancelled only by explicit modal/session lifecycle cancellation.
        signal?.removeEventListener('abort', abort);
      }
    },
    async checkConnection(platform: string): Promise<PlatformConnection> {
      const flow = platform === 'xhs' ? active : null;
      if (!flow) {
        const request = generation;
        const rows = (await readConnections()).filter(row => row.platform === platform);
        if (request !== generation) throw cancelled();
        if (rows.length !== 1) throw new ServiceError('CONNECTION_NOT_UNIQUE', '无法确认唯一的当前连接记录，请刷新列表并核对账号。');
        return rows[0];
      }
      const result = await flow.invoke({action: 'CHECK', platform: 'XIAOHONGSHU', flowId: flow.id});
      if (active !== flow) throw cancelled();
      if ('flowId' in result && result.flowId !== flow.id)
        throw new ServiceError('INVALID_SERVICE_RESPONSE', '连接响应尚未确认，请核对当前窗口后重试。');
      if (result.state === 'CONNECTED') return decodeConnectionRegistry({items: [result.connection]})[0];
      if (result.state === 'CANCELLED') active = null;
      throw failure(result);
    },
    async cancelConnection(platform: string): Promise<void> {
      if (platform !== 'xhs') return;
      generation++;
      const flow = active;
      active = null;
      if (flow) await cancelFlow(flow);
    },
  };
}
