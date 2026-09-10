// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {service} from '../../src/renderer/services/client';
afterEach(()=>vi.unstubAllGlobals());
it('only installs identity service when both narrow desktop methods exist and preserves stable identity',async()=>{
  vi.stubGlobal('yikeDesktop',{getDeviceIdentityStatus:vi.fn()});
  expect(service.deviceIdentity).toBeUndefined();
  const status={state:'NOT_PREPARED'};
  const getDeviceIdentityStatus=vi.fn().mockResolvedValue(status);
  const prepareDeviceIdentity=vi.fn().mockResolvedValue(status);
  vi.stubGlobal('yikeDesktop',{getDeviceIdentityStatus,prepareDeviceIdentity});
  const identity=service.deviceIdentity;
  expect(identity).toBeDefined();
  expect(identity).toBe(service.deviceIdentity);
  expect(await identity!.getStatus()).toEqual(status);
  await identity!.prepare({retryRegistration:true});
  expect(prepareDeviceIdentity).toHaveBeenCalledExactlyOnceWith({retryRegistration:true});
});
