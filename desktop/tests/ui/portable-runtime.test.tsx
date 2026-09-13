// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,render,screen} from '@testing-library/react';
import {PortableRuntimeNotice} from '../../src/renderer/pages/connections/PortableRuntimeNotice';
afterEach(()=>{cleanup();delete (window as any).yikeDesktop;});
it('shows preparation without claiming a connected platform',async()=>{
  (window as any).yikeDesktop={getPortableRuntimeStatus:vi.fn(async()=>({state:'PREPARING'}))};
  render(<PortableRuntimeNotice/>);expect(await screen.findByText('正在准备，请稍候…')).toBeTruthy();
});
it('shows actionable failure without an automatic repair or retry',async()=>{
  (window as any).yikeDesktop={getPortableRuntimeStatus:vi.fn(async()=>({state:'FAILED'}))};
  render(<PortableRuntimeNotice/>);expect(await screen.findByText('准备失败，请重新打开客户端；若仍失败，请联系支持。')).toBeTruthy();expect(screen.queryByRole('button')).toBeNull();
});
it('does not show technical readiness notices when preparation succeeds',async()=>{
  (window as any).yikeDesktop={getPortableRuntimeStatus:vi.fn(async()=>({state:'READY'}))};
  await act(async()=>{render(<PortableRuntimeNotice/>);});
  expect(screen.queryByRole('status')).toBeNull();
});
