// @vitest-environment jsdom
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {downloadText} from '../../src/renderer/services/download';
import type {YikeDesktopApi} from '../../src/shared/contracts';

const host = window as unknown as {yikeDesktop?: YikeDesktopApi};
const input = {format: 'csv' as const, name: 'TEST', content: 'TEST data'};
const createDescriptor = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
const revokeDescriptor = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');
let createUrl: ReturnType<typeof vi.fn>;
let revokeUrl: ReturnType<typeof vi.fn>;
beforeEach(() => {
  createUrl = vi.fn().mockReturnValue('blob:http://localhost/TEST'); revokeUrl = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', {configurable: true, value: createUrl});
  Object.defineProperty(URL, 'revokeObjectURL', {configurable: true, value: revokeUrl});
});
afterEach(() => {
  delete host.yikeDesktop; vi.useRealTimers(); vi.restoreAllMocks();
  if (createDescriptor) Object.defineProperty(URL, 'createObjectURL', createDescriptor); else Reflect.deleteProperty(URL, 'createObjectURL');
  if (revokeDescriptor) Object.defineProperty(URL, 'revokeObjectURL', revokeDescriptor); else Reflect.deleteProperty(URL, 'revokeObjectURL');
});
describe('download result contract', () => {
  it.each(['saved', 'cancelled'] as const)('preserves native %s without starting a browser download', async status => {
    const saveExport = vi.fn().mockResolvedValue({status});
    host.yikeDesktop = {saveExport} as unknown as YikeDesktopApi;
    expect(await downloadText(input)).toEqual({status});
    expect(saveExport).toHaveBeenCalledWith({...input, name: 'TEST.csv'});
    expect(createUrl).not.toHaveBeenCalled();
  });
  it('does not fall back to browser downloads when the native bridge is old or fails', async () => {
    host.yikeDesktop = {} as YikeDesktopApi;
    expect(await downloadText(input)).toEqual({status: 'error', error: 'EXPORT_UNAVAILABLE'});
    host.yikeDesktop = {saveExport: vi.fn().mockRejectedValue(new Error('/private/account/secret'))} as unknown as YikeDesktopApi;
    expect(await downloadText(input)).toEqual({status: 'error', error: 'EXPORT_FAILED'});
    expect(createUrl).not.toHaveBeenCalled();
  });
  it.each([
    {ok: true}, {status: 'saved-to-file'}, {status: 'error', error: '/private/secret'}, null,
  ])('rejects malformed native replies without returning raw details', async reply => {
    host.yikeDesktop = {saveExport: vi.fn().mockResolvedValue(reply)} as unknown as YikeDesktopApi;
    expect(await downloadText(input)).toEqual({status: 'error', error: 'EXPORT_FAILED'});
  });
  it('preserves a fixed native error code', async () => {
    host.yikeDesktop = {saveExport: vi.fn().mockResolvedValue({status: 'error', error: 'EXPORT_BUSY'})} as unknown as YikeDesktopApi;
    expect(await downloadText(input)).toEqual({status: 'error', error: 'EXPORT_BUSY'});
  });
  it('reports only initiated for a browser download and revokes its object URL', async () => {
    vi.useFakeTimers(); let filename = '';
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {filename = this.download;});
    expect(await downloadText(input)).toEqual({status: 'initiated'});
    expect(filename).toBe('TEST.csv');
    expect(createUrl.mock.calls[0][0].type).toBe('text/csv;charset=utf-8');
    await vi.runAllTimersAsync(); expect(revokeUrl).toHaveBeenCalledWith('blob:http://localhost/TEST');
  });
  it('uses a fixed backup extension and JSON MIME without claiming browser disk success', async () => {
    let filename = '';
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {filename = this.download;});
    expect(await downloadText({format: 'backup-json', name: 'TEST', content: '{"test":true}'})).toEqual({status: 'initiated'});
    expect(filename).toBe('TEST.yike-backup.json');
    expect(createUrl.mock.calls[0][0].type).toBe('application/json;charset=utf-8');
  });
  it('reports a blocked browser click as error and rejects invalid input before either transport', async () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {throw new Error('blocked');});
    expect(await downloadText(input)).toEqual({status: 'error', error: 'EXPORT_FAILED'});
    createUrl.mockClear();
    expect(await downloadText({...input, name: '../path'})).toEqual({status: 'error', error: 'INVALID_EXPORT_REQUEST'});
    expect(createUrl).not.toHaveBeenCalled();
  });
});
