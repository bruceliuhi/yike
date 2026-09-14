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
it('negotiated Bilibili monitor passes frozen query cursor and returns empty records plus true progress',async()=>{
  const f=fixture();f.input.target.platform='BILIBILI';f.input.snapshot.platforms=['BILIBILI'];
  Object.assign(f.input.snapshot.configuration,{mode:'monitor',schedule:{kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1}});
  const cursor={page:1,consumed_ids:['1','2'],refresh_next:false};
  const states=['设计','搭建'].map(query=>({query,revision:1,base_batch_request_id:id(30),cursor}));
  f.input.lease.native_progress={schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',plan_id:id(40),queries:states};
  const run=createPythonCollectionDriver({...f.options,allowMonitor:true,binding:{...f.options.binding,platform:'BILIBILI',expectedAccountPublicId:'123'}}).start(f.input);
  const deltas=[];
  for(let i=0;i<2;i++){
    await tick();expect(f.request(i).native_progress).toEqual({schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',...states[i]});
    const delta={query:states[i].query,revision:1,base_batch_request_id:id(30),before:cursor,after:{page:2,consumed_ids:[],refresh_next:true},
      page_ids:['1','2','3'],processed_ids:['3'],has_more:true,comments_scope:'BOUNDED_SAMPLE'};
    deltas.push(delta);f.respond(i,[],{native_progress:delta});
  }
  await expect(run.completed).resolves.toEqual({records:[],nativeProgress:{schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',claim_request_id:id(1),queries:deltas}});
  await run.stop();
});
it('fixed private spawn, no inherited secret, sequential query budgets and untouched formal evidence', async () => {
  vi.stubEnv('DATABASE_URL', 'secret'); vi.stubEnv('YIKE_AUTH_TOKEN', 'secret');
  const f = fixture(); const run = f.driver.start(f.input); await tick();
  expect(spawn).toHaveBeenCalledTimes(1);
  const [exe, args, options] = vi.mocked(spawn).mock.calls[0];
  expect(exe).toBe(f.options.pythonExecutable); expect(args).toEqual(['-B', '-X', 'utf8', '-m', 'app.windows_collection_host']);
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
it('runs every confirmed Bilibili link with null query, canonical target, identity, and one shared budget', async () => {
  const f = fixture();
  const links = [
    'https://www.bilibili.com/video/BV1d54y1g7db',
    'https://space.bilibili.com/123456',
  ];
  f.input.target.platform = 'BILIBILI';
  f.input.snapshot.platforms = ['BILIBILI'];
  f.input.snapshot.max_records = f.input.maxRecords = 3;
  Object.assign(f.input.snapshot.configuration, {source: 'links', keywords: [], links});
  const driver = createPythonCollectionDriver({...f.options, allowNativeLinks:true, binding: {...f.options.binding,
    platform: 'BILIBILI', expectedAccountPublicId: '123456'}} as any);
  const run = driver.start(f.input); await tick();
  expect(f.request(0)).toMatchObject({platform:'BILIBILI',query:null,max_records:2,expected_account_public_id:'123456',
    native_link:{platform:'BILIBILI',kind:'detail',external_id:'BV1d54y1g7db',canonical_url:links[0]}});
  f.respond(0, [{...record(),kind:'POST',external_comment_id:null,public_url:links[0],query:null}]); await tick();
  expect(f.request(1)).toMatchObject({query:null,max_records:2,native_link:{platform:'BILIBILI',kind:'creator',external_id:'123456',canonical_url:links[1]}});
  f.respond(1, [{...record(),external_source_id:'BV1d54y1g7db',external_comment_id:'1',public_url:links[0],query:null}]);
  await expect(run.completed).resolves.toHaveLength(2); await run.stop();
});
it('rejects Bilibili links before spawn when the shared record budget cannot cover every target', async () => {
  const f=fixture();f.input.target.platform='BILIBILI';f.input.snapshot.platforms=['BILIBILI'];f.input.maxRecords=1;
  Object.assign(f.input.snapshot.configuration,{source:'links',keywords:[],links:['https://www.bilibili.com/video/BV1d54y1g7db','https://space.bilibili.com/123456']});
  const run=createPythonCollectionDriver({...f.options,allowNativeLinks:true,binding:{...f.options.binding,platform:'BILIBILI',expectedAccountPublicId:'123456'}} as any).start(f.input);
  await expect(run.completed).rejects.toThrow('SOURCE_DRIVER_INVALID_INPUT');expect(spawn).not.toHaveBeenCalled();await run.stop();
});
it('rejects a parser-recognized but mapper-incompatible Bilibili BV before spawn',async()=>{
  const f=fixture();f.input.target.platform='BILIBILI';f.input.snapshot.platforms=['BILIBILI'];
  Object.assign(f.input.snapshot.configuration,{source:'links',keywords:[],links:['https://www.bilibili.com/video/BV0d54y1g7db']});
  const run=createPythonCollectionDriver({...f.options,allowNativeLinks:true,binding:{...f.options.binding,platform:'BILIBILI',expectedAccountPublicId:'123456'}} as any).start(f.input);
  await expect(run.completed).rejects.toThrow('SOURCE_DRIVER_INVALID_INPUT');expect(spawn).not.toHaveBeenCalled();await run.stop();
});
it.each([
  ['XIAOHONGSHU', ['找搭建团队']],
  ['BILIBILI', ['展台设计报价']],
  ['DOUYIN', ['设计', '搭建']],
] as const)('uses the confirmed platform-specific queries for %s with global fallback', async (platform, expected) => {
  const f = fixture();
  f.input.target.platform = platform;
  f.input.snapshot.platforms = ['XIAOHONGSHU', 'BILIBILI', 'DOUYIN'];
  f.input.snapshot.configuration.platformQueries = {version: 'platform-queries-v1', items: [
    {platform: 'XIAOHONGSHU', keywords: ['找搭建团队']},
    {platform: 'BILIBILI', keywords: ['展台设计报价']},
  ]};
  const binding = {...f.options.binding, platform};
  const run = createPythonCollectionDriver({...f.options, binding} as any).start(f.input);
  for (let index = 0; index < expected.length; index++) {
    await tick();
    expect(f.request(index).query).toBe(expected[index]);
    f.respond(index, [], {});
  }
  await expect(run.completed).resolves.toEqual([]);
  expect(spawn).toHaveBeenCalledTimes(expected.length);
  await run.stop();
});
it.each(['connection', 'research', 'links', 'comma', 'budget', 'platformScope'])('rejects unsupported/mismatched %s before spawn', async kind => {
  const f = fixture(); const c = f.input.snapshot.configuration;
  if (kind === 'connection') f.input.target.connection_version = 2;
  if (kind === 'research') c.research = {};
  if (kind === 'links') c.links = ['https://example.org'];
  if (kind === 'comma') c.keywords = ['设计,搭建'];
  if (kind === 'budget') f.input.maxRecords = 101;
  if (kind === 'platformScope') f.input.snapshot.configuration.platformQueries = {version: 'platform-queries-v1', items: [
    {platform: 'BILIBILI', keywords: ['展台设计报价']},
  ]};
  const run = f.driver.start(f.input); await expect(run.completed).rejects.toThrow('SOURCE_DRIVER_INVALID_INPUT'); await run.stop();
  expect(spawn).not.toHaveBeenCalled();
});
it('filters POST title/body and COMMENT body with literal NFC case-folding, without parent matching or budget refill', async () => {
  const f = fixture(); f.input.snapshot.configuration.keywords = ['设计'];
  f.input.snapshot.configuration.exclusions = ['CAFÉ', '招聘']; f.input.maxRecords = 4;
  const run = f.driver.start(f.input); await tick(); expect(f.request(0).max_records).toBe(4);
  const base = record();
  const postTitle = {...base, kind: 'POST', external_comment_id: null, title: 'cafe\u0301 项目', body: '保留正文'};
  const postBody = {...base, kind: 'POST', external_source_id: '66c21234abcdef0123456789', external_comment_id: null, title: '项目', body: '正在招聘'};
  const commentBody = {...base, external_comment_id: '66c31234abcdef0123456789', body: 'CaFé 咨询'};
  const parentOnly = {...base, external_comment_id: '66c41234abcdef0123456789', body: '真实需求', parent: {
    external_comment_id: '66c51234abcdef0123456789', body: '招聘信息', author_public_id: null, published_at: null, public_url: null}};
  f.respond(0, [postTitle, postBody, commentBody, parentOnly]);
  expect(await run.completed).toEqual([parentOnly]); expect(spawn).toHaveBeenCalledTimes(1); await run.stop();
});
it('rejects conflicting duplicate evidence even when every version is excluded', async () => {
  const f = fixture(); f.input.snapshot.configuration.exclusions = ['原文'];
  const run = f.driver.start(f.input); const outcome = run.completed.catch(error => error.message); await tick();
  f.respond(0, [record()]); await tick();
  f.respond(1, [{...record('搭建'), body: '原文 已修改'}]);
  expect(await outcome).toBe('SOURCE_DRIVER_CONFLICT'); await run.stop();
});
it('returns a successful empty result when raw excluded records exhaust the budget without replacement collection', async () => {
  const f = fixture(); f.input.snapshot.configuration.keywords = ['设计', '搭建', '布展'];
  f.input.snapshot.configuration.exclusions = ['原文']; f.input.maxRecords = 2;
  const run = f.driver.start(f.input); await tick(); expect(f.request(0).max_records).toBe(1);
  f.respond(0, [record()]); await tick(); expect(f.request(1).max_records).toBe(1);
  f.respond(1, [record('搭建', '66c21234abcdef0123456789')]);
  await expect(run.completed).resolves.toEqual([]); expect(spawn).toHaveBeenCalledTimes(2); await run.stop();
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
it('offline candidate mapping rejection does not poison a clean host stop', async () => {
  const f = fixture(); const run = f.driver.start(f.input); const outcome = run.completed.catch(e => e.message); await tick();
  f.children[0].stdout.write(JSON.stringify({schema_version, state: 'FAILED', error_code: 'COLLECTION_PARSE_FAILED'}) + '\n');
  f.children[0].emit('close', 0, null);
  expect(await outcome).toBe('SOURCE_DRIVER_FAILED');
  await expect(run.stop()).resolves.toBeUndefined();
  expect(f.children).toHaveLength(1); // Never continue the next query after a rejected batch.
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
it('forwards main-owned canonical XHS account binding on every query, but omits legacy binding', async () => {
  const f = fixture(); const account = '66c01234abcdef0123456789';
  const driver = createPythonCollectionDriver({...f.options, binding: {...f.options.binding, expectedAccountPublicId: account}});
  const run = driver.start(f.input); await tick(); expect(f.request(0).expected_account_public_id).toBe(account);
  f.respond(0); await tick(); expect(f.request(1).expected_account_public_id).toBe(account);
  f.respond(1); await expect(run.completed).resolves.toEqual([]); await run.stop();
  const g = fixture(); g.input.snapshot.configuration.keywords = ['设计'];
  const legacy = g.driver.start(g.input); await tick(); expect(g.request(0)).not.toHaveProperty('expected_account_public_id');
  g.respond(0); await legacy.completed; await legacy.stop();
});
it.each(['short', 'a'.repeat(33), '汉字12345678', 'abcdefgh\n', ' abcdefgh', null, 12345678])
('rejects invalid account binding %s before spawn', async value => {
  const f = fixture();
  const binding = {...f.options.binding, expectedAccountPublicId: value} as any;
  const run = createPythonCollectionDriver({...f.options, binding}).start(f.input);
  const outcome = run.completed.catch(error => error.message); await tick();
  expect(spawn).not.toHaveBeenCalled(); expect(await outcome).toBe('SOURCE_DRIVER_INVALID_INPUT'); await run.stop();
});
it.each([['DOUYIN','douyin.account-1'],['BILIBILI','123456789']] as const)
('forwards the selected %s expected account without changing the host wire field',async(platform,account)=>{
 const f=fixture();f.input.target.platform=platform;f.input.snapshot.platforms=[platform];
 const binding={...f.options.binding,platform,expectedAccountPublicId:account};
 const run=createPythonCollectionDriver({...f.options,binding} as any).start(f.input);await tick();
 expect(f.request(0)).toMatchObject({platform,expected_account_public_id:account});f.respond(0);await tick();f.respond(1);
 await run.completed;await run.stop();
});
it('allows one policyVersion 1 monitor iteration only when main marks the driver binding',async()=>{
 const f=fixture();f.input.snapshot.configuration.mode='monitor';f.input.snapshot.configuration.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const run=createPythonCollectionDriver({...f.options,allowMonitor:true}).start(f.input);await tick();expect(spawn).toHaveBeenCalledTimes(1);
 f.respond(0);await tick();f.respond(1);await run.completed;await run.stop();
 const g=fixture();g.input.snapshot.configuration.mode='monitor';g.input.snapshot.configuration.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const rejected=g.driver.start(g.input);await expect(rejected.completed).rejects.toThrow('SOURCE_DRIVER_INVALID_INPUT');expect(g.children).toHaveLength(0);
});
