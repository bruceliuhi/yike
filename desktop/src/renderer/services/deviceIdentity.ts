import type {YikeDesktopApi} from '../../shared/contracts';
import type {DeviceIdentityRetry,DeviceIdentityStatus} from '../../shared/deviceIdentity';

export interface DeviceIdentityApi {
  getStatus(): Promise<DeviceIdentityStatus>;
  prepare(options: DeviceIdentityRetry): Promise<DeviceIdentityStatus>;
}
const cache = new WeakMap<YikeDesktopApi,DeviceIdentityApi>();
export function desktopDeviceIdentity(bridge: YikeDesktopApi | undefined): DeviceIdentityApi | undefined {
  if (!bridge || typeof bridge.getDeviceIdentityStatus !== 'function' || typeof bridge.prepareDeviceIdentity !== 'function') return undefined;
  const previous=cache.get(bridge);
  if(previous) return previous;
  const read=bridge.getDeviceIdentityStatus, prepare=bridge.prepareDeviceIdentity;
  const api=Object.freeze({getStatus:()=>read(),prepare:(options:DeviceIdentityRetry)=>prepare(options)});
  cache.set(bridge,api);
  return api;
}
