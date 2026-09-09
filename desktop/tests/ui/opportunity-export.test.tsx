// @vitest-environment jsdom
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {OpportunitiesPage, PUBLIC_SAMPLE} from '../../src/renderer/pages/Opportunities';
import {downloadText, type DownloadResult} from '../../src/renderer/services/download';
import {parseRoute} from '../../src/renderer/domain/routes';
import type {AppContextValue} from '../../src/renderer/app/context';
import type {YikeService} from '../../src/renderer/services/contracts';

let context: AppContextValue;
vi.mock('../../src/renderer/app/context', () => ({useApp: () => context}));
vi.mock('../../src/renderer/services/download', () => ({downloadText: vi.fn(), downloadErrorMessage: () => '文件未能保存，请检查保存位置后重试。'}));
const customer = {...PUBLIC_SAMPLE, id: 'TEST-customer', sample: false, title: 'TEST 客户询价'};
beforeEach(() => {
  vi.mocked(downloadText).mockReset();
  context = {service: {opportunities: vi.fn().mockResolvedValue([customer, PUBLIC_SAMPLE])} as unknown as YikeService,
    session: {authenticated: true, userId: 'TEST-export'}, route: parseRoute('#/opportunities'),
    navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn()};
});
afterEach(cleanup);
async function selectCustomer() {
  fireEvent.click(await screen.findByRole('checkbox', {name: '选择TEST 客户询价'}));
}
describe('customer CSV native receipt', () => {
  it('waits for actual saved receipt, blocks repeated clicks, and only includes selected customers', async () => {
    let resolve!: (result: DownloadResult) => void;
    vi.mocked(downloadText).mockImplementation(() => new Promise(done => {resolve = done;}));
    render(<OpportunitiesPage />); await selectCustomer();
    const button = screen.getByRole('button', {name: '导出所选客户商机'});
    fireEvent.click(button); fireEvent.click(button);
    expect(downloadText).toHaveBeenCalledOnce(); expect(context.notify).not.toHaveBeenCalled();
    expect((screen.getByRole('button', {name: '正在保存…'}) as HTMLButtonElement).disabled).toBe(true);
    const request = vi.mocked(downloadText).mock.calls[0][0];
    expect(request).toMatchObject({format: 'csv', name: '意客AI-客户商机.csv'});
    expect(request.content).toContain(customer.title); expect(request.content).not.toContain(PUBLIC_SAMPLE.title);
    await act(async () => {resolve({status: 'saved'});});
    expect(context.notify).toHaveBeenCalledWith('已保存 1 条选中客户商机。', 'success');
  });
  it('keeps selection and never shows success when the user cancels', async () => {
    vi.mocked(downloadText).mockResolvedValue({status: 'cancelled'});
    render(<OpportunitiesPage />); await selectCustomer();
    fireEvent.click(screen.getByRole('button', {name: '导出所选客户商机'}));
    await waitFor(() => expect((screen.getByRole('button', {name: '导出所选客户商机'}) as HTMLButtonElement).disabled).toBe(false));
    expect(context.notify).not.toHaveBeenCalled();
    expect((screen.getByRole('checkbox', {name: '选择TEST 客户询价'}) as HTMLInputElement).checked).toBe(true);
  });
  it('keeps selection after disk failure and exposes only the friendly error', async () => {
    vi.mocked(downloadText).mockResolvedValue({status: 'error', error: 'EXPORT_FAILED'});
    render(<OpportunitiesPage />); await selectCustomer();
    fireEvent.click(screen.getByRole('button', {name: '导出所选客户商机'}));
    await waitFor(() => expect(context.notify).toHaveBeenCalledWith('文件未能保存，请检查保存位置后重试。', 'error'));
    expect((screen.getByRole('checkbox', {name: '选择TEST 客户询价'}) as HTMLInputElement).checked).toBe(true);
  });
  it('reports browser initiation as info instead of disk success', async () => {
    vi.mocked(downloadText).mockResolvedValue({status: 'initiated'});
    render(<OpportunitiesPage />); await selectCustomer();
    fireEvent.click(screen.getByRole('button', {name: '导出所选客户商机'}));
    await waitFor(() => expect(context.notify).toHaveBeenCalledWith('已发起 1 条客户商机的下载，请在浏览器中确认。', 'info'));
  });
  it('does not export public sample rows', async () => {
    context.route = parseRoute('#/opportunities?scope=sample');
    render(<OpportunitiesPage />); await screen.findByText(PUBLIC_SAMPLE.title);
    fireEvent.click(screen.getByRole('button', {name: '导出所选客户商机'}));
    expect(downloadText).not.toHaveBeenCalled();
  });
  it('does not publish a late success after the customer page unmounts', async () => {
    let resolve!: (result: DownloadResult) => void;
    vi.mocked(downloadText).mockImplementation(() => new Promise(done => {resolve = done;}));
    const mounted = render(<OpportunitiesPage />); await selectCustomer();
    fireEvent.click(screen.getByRole('button', {name: '导出所选客户商机'}));
    mounted.unmount(); await act(async () => {resolve({status: 'saved'});});
    expect(context.notify).not.toHaveBeenCalled();
  });
});
