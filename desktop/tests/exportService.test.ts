import {afterEach, describe, expect, it, vi} from 'vitest';
import {mkdtemp, mkdir, readFile, readdir, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createExportHandler, writeExportFile} from '../src/main/exportService';
import {MAX_EXPORT_BYTES, validatedExport} from '../src/shared/exportValidation';

const request = {format: 'csv' as const, name: '意客AI-客户商机.csv', content: '\uFEFF"标题"\r\n"TEST"'};
const roots: string[] = [];
async function folder() {const root = await mkdtemp(path.join(os.tmpdir(), 'yike-export-test-')); roots.push(root); return root;}
afterEach(async () => {await Promise.all(roots.splice(0).map(root => rm(root, {recursive: true, force: true})));});

describe('fixed export payload', () => {
  it('normalizes only supported extensions and validates UTF-8 byte length', () => {
    expect(validatedExport({...request, name: '意客AI 2026'})).toMatchObject({name: '意客AI 2026.csv'});
    expect(validatedExport({...request, name: 'report.CSV'})).toMatchObject({name: 'report.csv'});
    expect(validatedExport({...request, content: 'x'.repeat(MAX_EXPORT_BYTES)})).not.toBeNull();
    expect(validatedExport({...request, content: 'x'.repeat(MAX_EXPORT_BYTES + 1)})).toBeNull();
    expect(validatedExport({...request, content: '中'.repeat(700_000)})).toBeNull();
  });
  it.each(['../secret','/tmp/file','C:\\secret','name/path','name\\path','.hidden','a..b','NUL','CON.txt','报告\n隐藏'])('rejects path or unsafe name %s', name => {
    expect(validatedExport({...request, name})).toBeNull();
  });
  it('rejects arbitrary fields, executable format, NUL, and non-object backups', () => {
    for (const input of [null, [], {...request, path: '/tmp/arbitrary.csv'}, {...request, format: 'html'},
      {...request, content: 'a\0b'}, {...request, content: ''}]) expect(validatedExport(input)).toBeNull();
    for (const content of ['null', '[]', '"value"', '42', 'invalid'])
      expect(validatedExport({format: 'backup-json', name: '备份', content})).toBeNull();
    expect(validatedExport({format: 'backup-json', name: '意客AI备份', content: '{"version":1}'}))
      .toEqual({format: 'backup-json', name: '意客AI备份.yike-backup.json', content: '{"version":1}'});
  });
});

describe('native save handler', () => {
  it('returns saved only after actual temporary-file write and preserves exact UTF-8 bytes', async () => {
    const root = await folder(); const destination = path.join(root, '客户.csv');
    await writeFile(destination, 'old export');
    const chooseFile = vi.fn().mockResolvedValue({canceled: false, filePath: destination});
    const handler = createExportHandler({isTrusted: () => true, chooseFile, writeFile: writeExportFile});
    expect(await handler({}, request)).toEqual({status: 'saved'});
    expect(await readFile(destination)).toEqual(Buffer.from(request.content, 'utf8'));
    expect(await readdir(root)).toEqual(['客户.csv']);
    expect(chooseFile.mock.calls[0][1]).toEqual(request);
  });
  it('uses the backup extension and never returns the selected absolute path', async () => {
    const root = await folder(); const destination = path.join(root, 'TEST.yike-backup.json');
    const handler = createExportHandler({isTrusted: () => true,
      chooseFile: async () => ({canceled: false, filePath: destination}), writeFile: writeExportFile});
    const result = await handler({}, {format: 'backup-json', name: 'TEST', content: '{"test":true}'});
    expect(result).toEqual({status: 'saved'});
    expect(JSON.parse(await readFile(destination, 'utf8'))).toEqual({test: true});
    expect(JSON.stringify(result)).not.toContain(root);
  });
  it('rejects untrusted sender before opening a dialog and rejects extra paths', async () => {
    const chooseFile = vi.fn(); const write = vi.fn();
    const handler = createExportHandler({isTrusted: (trusted: boolean) => trusted, chooseFile, writeFile: write});
    expect(await handler(false, request)).toEqual({status: 'error', error: 'UNTRUSTED_SENDER'});
    expect(await handler(true, {...request, path: '/private/output.csv'})).toEqual({status: 'error', error: 'INVALID_EXPORT_REQUEST'});
    expect(chooseFile).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled();
  });
  it('cancellation never writes and permits a later request', async () => {
    const chooseFile = vi.fn().mockResolvedValue({canceled: true}); const write = vi.fn();
    const handler = createExportHandler({isTrusted: () => true, chooseFile, writeFile: write});
    expect(await handler({}, request)).toEqual({status: 'cancelled'});
    expect(await handler({}, request)).toEqual({status: 'cancelled'});
    expect(chooseFile).toHaveBeenCalledTimes(2); expect(write).not.toHaveBeenCalled();
  });
  it('keeps one dialog active and does not queue duplicate requests', async () => {
    let resolve!: (result: {canceled: boolean}) => void;
    const chooseFile = vi.fn(() => new Promise<{canceled: boolean}>(done => {resolve = done;}));
    const handler = createExportHandler({isTrusted: () => true, chooseFile, writeFile: vi.fn()});
    const pending = handler({}, request);
    expect(await handler({}, request)).toEqual({status: 'error', error: 'EXPORT_BUSY'});
    expect(chooseFile).toHaveBeenCalledTimes(1);
    resolve({canceled: true}); expect(await pending).toEqual({status: 'cancelled'});
  });
  it('does not write after the originating frame becomes untrusted during the dialog', async () => {
    let trusted = true; const write = vi.fn();
    const handler = createExportHandler({isTrusted: () => trusted,
      chooseFile: async () => {trusted = false; return {canceled: false, filePath: path.resolve('unused.csv')};}, writeFile: write});
    expect(await handler({}, request)).toEqual({status: 'error', error: 'UNTRUSTED_SENDER'});
    expect(write).not.toHaveBeenCalled();
  });
  it.each([undefined, 'relative.csv', path.resolve('wrong.exe'), path.resolve('backup.json')])('rejects a destination with the wrong extension or shape', async filePath => {
    const write = vi.fn(); const handler = createExportHandler({isTrusted: () => true,
      chooseFile: async () => ({canceled: false, filePath}), writeFile: write});
    expect(await handler({}, request)).toEqual({status: 'error', error: 'INVALID_EXPORT_DESTINATION'});
    expect(write).not.toHaveBeenCalled();
  });
  it('does not report success while disk write is pending and sanitizes write failures', async () => {
    let reject!: (error: Error) => void;
    const write = vi.fn(() => new Promise<void>((_resolve, fail) => {reject = fail;}));
    const handler = createExportHandler({isTrusted: () => true,
      chooseFile: async () => ({canceled: false, filePath: path.resolve('unused.csv')}), writeFile: write});
    let completed = false; const pending = handler({}, request).then(result => {completed = true; return result;});
    await vi.waitFor(() => expect(write).toHaveBeenCalledOnce()); expect(completed).toBe(false);
    reject(new Error('private/path/SECRET ENOSPC'));
    expect(await pending).toEqual({status: 'error', error: 'EXPORT_FAILED'});
    expect(await handler({}, {...request, content: ''})).toMatchObject({error: 'INVALID_EXPORT_REQUEST'});
  });
  it('cleans temporary data if atomic replacement fails and leaves the destination intact', async () => {
    const root = await folder(); const destination = path.join(root, 'directory.csv');
    await mkdir(destination); await writeFile(path.join(destination, 'keep.txt'), 'keep');
    await expect(writeExportFile(destination, request.content)).rejects.toThrow();
    expect(await readdir(root)).toEqual(['directory.csv']);
    expect(await readFile(path.join(destination, 'keep.txt'), 'utf8')).toBe('keep');
  });
});
