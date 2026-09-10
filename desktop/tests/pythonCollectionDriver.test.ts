import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {spawn} from 'node:child_process';
import {createPythonCollectionDriver} from '../src/main/pythonCollectionDriver';
vi.mock('node:child_process', () => ({spawn: vi.fn()}));
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const schema_version = 'windows-source-host-v1';
function fixture() {
  const children: any[] = [];
  vi.mocked(spawn).mockImplementation(() => {
    const child = Object.assign(new EventEmitter(), {stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), kill: vi.fn()});
    children.push(child); return child as any;
  });
  const target = {platform: 'XIAOHONGSHU' as const, access_mode: 'PLATFORM_ACCOUNT' as const, connection_id: id(5), connection_version: 1};
  const options = {pythonExecutable: 'C:\\test\\python.exe', projectRoot: 'C:\\project', runtimePath: 'C:\\runtime', profilePath: 'C:\\profile', outputRoot: 'C:\\output',
    binding: {deviceId: id(2), credentialVersion: 1, ...target}};
  const abort = new AbortController();
  const input: any = {snapshot: {profile_version_id: id(3), strategy_version_id: id(4), platforms: ['XIAOHONGSHU'], max_records: 4, max_runtime_seconds: 300,
    configuration: {schema_version: 'research-strategy-v1', name: '原文', source: 'search', keywords: ['设计', '搭建'], exclusions: [], links: [], mode: 'once', schedule: null, research: null}},
    target, lease: {schema_version: 'execution-runtime-v1', operation: 'CLAIM', request_id: id(1), task_id: id(6), run_id: id(7), platform_run_id: id(8),
      status: 'RUNNING', stop_confirmed: false, lease_id: id(9), execution_generation: 1,
      lease_expires_at: new Date(Date.now() + 120000).toISOString(), deadline_at: new Date(Date.now() + 300000).toISOString()}, maxRecords: 4, signal: abort.signal};
  const driver = createPythonCollectionDriver(options);
  const request = (index: number) => JSON.parse(children[index].stdin.read().toString());
  const respond = (index: number, records: any[] = [], extra = {}) => {children[index].stdout.write(JSON.stringify({schema_version, state: 'COLLECTED', records, ...extra}) + '\n'); children[index].emit('close', 0, null);};
  return {driver, options, input, children, abort, request, respond};
}
function record(query = '设计', comment = '66c11234abcdef0123456789') {return {kind: 'COMMENT', external_source_id: '66c01234abcdef0123456789', external_comment_id: comment,
  public_url: 'https://www.xiaohongshu.com/explore/66c01234abcdef0123456789', title: null, author_public_id: null, body: '  原文 é😀\n\t ',
  published_at: null, observed_at: '2026-09-10T00:00:00Z', parent: null, collector_version: 'mediacrawler-test', normalizer_version: 'test-v1', query};}
beforeEach(() => {vi.clearAllMocks(); vi.useFakeTimers();});
afterEach(() => {vi.useRealTimers(); vi.unstubAllEnvs();});
const tick = () => vi.advanceTimersByTimeAsync(0);
it('fixed private spawn, no inherited secret, sequential query budgets and untouched formal evidence', async () => {
  vi.stubEnv('DATABASE_URL', 'secret'); vi.stubEnv('YIKE_AUTH_TOKEN', 'secret');
  const f = fixture(); const run = f.driver.start(f.input); await tick();
  expect(spawn).toHaveBeenCalledTimes(1);
  const [exe, args, options] = vi.mocked(spawn).mock.calls[0];
  expect(exe).toBe(f.options.pythonExecutable); expect(args).toEqual(['-X', 'utf8', '-m', 'app.windows_collection_host']);
  expect(options).toMatchObject({cwd: f.options.projectRoot, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe']});
  expect(options!.env).not.toHaveProperty('DATABASE_URL'); expect(options!.env).not.toHaveProperty('YIKE_AUTH_TOKEN');
  const first = f.request(0); expect(first).toMatchObject({schema_version, platform: 'XIAOHONGSHU', query: '设计', max_records: 2,
    mapping: {profile_version_id: id(3), execution: {device_id: id(2), lease_id: id(9), connection_id: id(5)}}});
  expect(f.children[0].stdin.writableEnded).toBe(false);
  f.respond(0, [record()]); await tick();
  expect(spawn).toHaveBeenCalledTimes(2); const second = f.request(1);
  expect(second.query).toBe('搭建'); expect(second.max_records).toBe(3); expect(second.output_path).not.toBe(first.output_path);
  f.respond(1, [record('搭建', '66c21234abcdef0123456789')]);
  expect(await run.completed).toEqual([record(), record('搭建', '66c21234abcdef0123456789')]); await run.stop();
});
it.each(['connection', 'exclusions', 'research', 'links', 'comma', 'budget'])('rejects unsupported/mismatched %s before spawn', async kind => {
  const f = fixture(); const c = f.input.snapshot.configuration;
  if (kind === 'connection') f.input.target.connection_version = 2;
  if (kind === 'exclusions') c.exclusions = ['招聘'];
  if (kind === 'research') c.research = {};
  if (kind === 'links') c.links = ['https://example.org'];
  if (kind === 'comma') c.keywords = ['设计,搭建'];
  if (kind === 'budget') f.input.maxRecords = 101;
  const run = f.driver.start(f.input); await expect(run.completed).rejects.toThrow('SOURCE_DRIVER_INVALID_INPUT'); await run.stop();
  expect(spawn).not.toHaveBeenCalled();
});
it('EOF cancellation waits for host cleanup/close and does not start next query', async () => {
  const f = fixture(); const run = f.driver.start(f.input); const outcome = run.completed.catch(e => e.message); await tick();
  f.abort.abort(); let stopped = false; const stop = run.stop().then(() => {stopped = true;}); await tick();
  expect(f.children[0].stdin.writableEnded).toBe(true); expect(stopped).toBe(false);
  f.children[0].stdout.write(JSON.stringify({schema_version, state: 'CANCELLED'}) + '\n'); f.children[0].emit('close', 0, null);
  await stop; expect(await outcome).toBe('SOURCE_DRIVER_CANCELLED'); expect(spawn).toHaveBeenCalledTimes(1);
});
it('forced host termination never confirms physical stop', async () => {
  const f = fixture(); const run = f.driver.start(f.input); void run.completed.catch(() => {}); await tick();
  const stop = run.stop(); const assertion = expect(stop).rejects.toThrow('SOURCE_STOP_FAILED');
  await vi.advanceTimersByTimeAsync(30000); await assertion; expect(f.children[0].kill).toHaveBeenCalledTimes(1);
  await expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
});
it.each(['extra', 'invalid', 'oversize', 'exit', 'state'])('rejects %s response with fixed sanitized error', async kind => {
  const f = fixture(); const run = f.driver.start(f.input); const outcome = run.completed.catch(e => e.message); await tick();
  if (kind === 'extra') f.respond(0, [], {token: 'secret'});
  if (kind === 'invalid') f.respond(0, [{...record(), body: null}]);
  if (kind === 'oversize') {f.children[0].stdout.write('a'.repeat(4 * 1024 * 1024 + 1)); f.children[0].emit('close', 0, null);}
  if (kind === 'exit') {f.children[0].stderr.write('secret'); f.children[0].emit('close', 1, null);}
  if (kind === 'state') {f.children[0].stdout.write(JSON.stringify({schema_version, state: 'SUCCEEDED'}) + '\n'); f.children[0].emit('close', 0, null);}
  expect(await outcome).toBe('SOURCE_DRIVER_FAILED');
  if (kind === 'exit') await expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED'); else await run.stop();
  expect(spawn).toHaveBeenCalledTimes(1);
});
it('deduplicates identical observations across queries but rejects conflicting evidence', async () => {
  const f = fixture(); const run = f.driver.start(f.input); await tick(); f.respond(0, [record()]); await tick();
  f.respond(1, [{...record('搭建'), observed_at: '2026-09-10T00:01:00Z'}]); expect(await run.completed).toEqual([record()]); await run.stop();
  const g = fixture(); const other = g.driver.start(g.input); const error = other.completed.catch(e => e.message); await tick(); g.respond(0, [record()]); await tick();
  g.respond(1, [{...record('搭建'), body: '已改'}]); expect(await error).toBe('SOURCE_DRIVER_CONFLICT'); await other.stop();
});
it('duplicate observations consume the shared budget instead of refunding it', async () => {
  const f = fixture(); f.input.snapshot.configuration.keywords = ['设计', '搭建', '布展'];
  const run = f.driver.start(f.input); await tick(); expect(f.request(0).max_records).toBe(2);
  f.respond(0, [record(), record('设计', '66c21234abcdef0123456789')]); await tick(); expect(f.request(1).max_records).toBe(1);
  f.respond(1, [record('搭建')]); await tick(); expect(f.request(2).max_records).toBe(1);
  f.respond(2, [record('布展', '66c31234abcdef0123456789')]); expect(await run.completed).toHaveLength(3); await run.stop();
});
it('unknown cleanup from host is not a confirmed physical stop', async () => {
  const f = fixture(); const run = f.driver.start(f.input); const outcome = run.completed.catch(e => e.message); await tick();
  f.children[0].stdout.write(JSON.stringify({schema_version, state: 'FAILED', error_code: 'SOURCE_HOST_FAILED'}) + '\n'); f.children[0].emit('close', 0, null);
  expect(await outcome).toBe('SOURCE_DRIVER_FAILED'); await expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
});
it('one second is a usable budget and total deadline cancels the host', async () => {
  const f = fixture(); f.input.snapshot.max_runtime_seconds = 1;
  const now = vi.spyOn(performance, 'now'); now.mockReturnValueOnce(0).mockReturnValueOnce(0.2);
  const run = f.driver.start(f.input); const outcome = run.completed.catch(e => e.message); await tick();
  expect(f.children).toHaveLength(1); expect(f.request(0).timeout_seconds).toBe(1);
  await vi.advanceTimersByTimeAsync(1000); expect(f.children[0].stdin.writableEnded).toBe(true);
  f.children[0].stdout.write(JSON.stringify({schema_version, state: 'CANCELLED'}) + '\n'); f.children[0].emit('close', 0, null);
  expect(await outcome).toBe('SOURCE_DRIVER_TIMED_OUT'); await run.stop(); now.mockRestore();
});
