// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {PortableRuntimeNotice} from '../../src/renderer/pages/connections/PortableRuntimeNotice';
afterEach(()=>{cleanup();delete (window as any).yikeDesktop;});
it('shows preparation without claiming a connected platform',async()=>{
  (window as any).yikeDesktop={getPortableRuntimeStatus:vi.fn(async()=>({state:'PREPARING'}))};
  render(<PortableRuntimeNotice/>);expect(await screen.findByText(/正在准备本机运行环境/)).toBeTruthy();
});
it('shows actionable failure without an automatic repair or retry',async()=>{
  (window as any).yikeDesktop={getPortableRuntimeStatus:vi.fn(async()=>({state:'FAILED'}))};
  render(<PortableRuntimeNotice/>);expect(await screen.findByText(/本机运行环境准备失败/)).toBeTruthy();expect(screen.queryByRole('button')).toBeNull();
});
