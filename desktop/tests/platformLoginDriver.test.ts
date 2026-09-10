import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {lstatSync} from 'node:fs';

vi.mock('node:fs', () => ({lstatSync: vi.fn()}));
const schema_version = 'windows-platform-login-v1';
const profileId = '00000000-0000-4000-8000-000000000001';
const opened = {schema_version, state: 'OPENED'};
const authenticated = {schema_version, state: 'AUTHENTICATED', account_public_id: 'abc12345', checked_at: '2026-09-10T01:02:03Z'};
const tick = () => vi.advanceTimersByTimeAsync(0);
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(lstatSync).mockImplementation((p: any) => ({isFile: () => String(p).endsWith('.exe'),
    isDirectory: () => !String(p).endsWith('.exe'), isSymbolicLink: () => false}) as any);
});
afterEach(() => {vi.useRealTimers(); vi.unstubAllEnvs(); vi.clearAllMocks();});

async function fixture(changes = {}) {
  const module = await import('../src/main/platformLoginDriver').catch(() => null);
  expect(module, 'main-only login driver must exist').not.toBeNull();
  const children: any[] = [];
  const spawn = vi.fn(() => {
    const child = Object.assign(new EventEmitter(), {stdin: new PassThrough(), stdout: new PassThrough(),
      stderr: new PassThrough(), kill: vi.fn()});
    children.push(child); return child as any;
  });
  const options = {pythonExecutable: 'C:\\test\\python.exe', projectRoot: 'C:\\project', runtimePath: 'C:\\runtime',
    profileRoot: 'C:\\private\\profiles', outputRoot: 'C:\\private\\outputs', spawn, ...changes};
  const driver = module!.createPlatformLoginDriver(options);
  const frame = (value: unknown) => children[0].stdout.write(JSON.stringify(value) + '\n');
  const close = (code = 0) => children[0].emit('close', code, null);
  return {driver, spawn, options, children, frame, close};
}

it('uses a fixed six-field request and secret-free spawn, holds stdin and waits physical close', async () => {
  vi.stubEnv('DATABASE_URL', 'secret'); vi.stubEnv('YIKE_AUTH_TOKEN', 'secret'); vi.stubEnv('PYTHONPATH', 'untrusted');
  const f = await fixture(); const run = f.driver.start({profileId}); await tick();
  expect(f.spawn).toHaveBeenCalledTimes(1);
  expect(f.spawn.mock.calls[0]).toEqual([f.options.pythonExecutable, ['-B', '-X', 'utf8', '-m', 'app.windows_platform_login'],
    expect.objectContaining({cwd: f.options.projectRoot, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe']})]);
  const env = (f.spawn.mock.calls[0] as any)[2].env;
  for (const key of ['DATABASE_URL', 'YIKE_AUTH_TOKEN', 'PYTHONPATH', 'PATH']) expect(env).not.toHaveProperty(key);
  const request = JSON.parse(f.children[0].stdin.read().toString());
  expect(Object.keys(request).sort()).toEqual(['schema_version','runtime_path','profile_path','output_path','platform','timeout_seconds'].sort());
  expect(request).toMatchObject({schema_version, runtime_path: f.options.runtimePath,
    profile_path: f.options.profileRoot + '\\' + profileId, platform: 'XIAOHONGSHU', timeout_seconds: 180});
  expect(request.output_path).toMatch(/^C:\\private\\outputs\\[a-f0-9-]{36}$/);
  expect(f.children[0].stdin.writableEnded).toBe(false);
  let done = false; void run.completed.then(() => {done = true;});
  f.frame(opened); await run.opened; f.frame(authenticated); await tick(); expect(done).toBe(false);
  f.children[0].emit('exit', 0, null); await tick(); expect(done).toBe(false);
  f.close(); expect(await run.completed).toEqual({account_public_id: 'abc12345', checked_at: authenticated.checked_at});
  await run.stop();
});

it.each([
  ['DOUYIN', 'owner.handle-1'],
  ['BILIBILI', '1234567890'],
] as const)('sends %s and accepts only its account identity', async (platform, account_public_id) => {
  const f = await fixture(); const run = f.driver.start({profileId, platform}); await tick();
  expect(JSON.parse(f.children[0].stdin.read().toString()).platform).toBe(platform);
  f.frame(opened); f.frame({...authenticated, account_public_id}); f.close();
  expect(await run.completed).toMatchObject({account_public_id});
});

it.each([
  ['DOUYIN', 'bad handle'],
  ['BILIBILI', 'abc12345'],
] as const)('rejects an invalid %s terminal account', async (platform, account_public_id) => {
  const f = await fixture(); const run = f.driver.start({profileId, platform}); await tick();
  f.frame(opened); f.frame({...authenticated, account_public_id}); f.close();
  await expect(run.completed).rejects.toThrow('SOURCE_HOST_FAILED');
});

it.each(['badProfile','missingRoot','relative','overlap'])('rejects %s configuration before spawning', async kind => {
  const f = await fixture(kind === 'relative' ? {runtimePath: 'relative'} : kind === 'overlap' ? {outputRoot: 'C:\\private\\profiles'} : {});
  if (kind === 'missingRoot') vi.mocked(lstatSync).mockImplementation(() => {throw new Error('private path');});
  const run = f.driver.start({profileId: kind === 'badProfile' ? '../escape' : profileId});
  await expect(run.completed).rejects.toThrow('PLATFORM_LOGIN_INPUT_INVALID');
  await expect(run.opened).rejects.toThrow('PLATFORM_LOGIN_INPUT_INVALID');
  await run.stop(); expect(f.spawn).not.toHaveBeenCalled();
});

it.each(['noOpened','duplicateOpened','duplicateTerminal','unknownField','invalidId','invalidTime','duplicateKey','invalidUtf8','oversize','truncated','exit'])
('fails closed for %s and never leaks stderr', async kind => {
  const f = await fixture(); const run = f.driver.start({profileId}); const outcome = run.completed.catch(e => e.message); await tick();
  f.children[0].stderr.write('token=private-secret');
  if (kind !== 'noOpened') f.frame(opened);
  if (kind === 'duplicateOpened') f.frame(opened);
  if (kind === 'unknownField') f.frame({...authenticated, token: 'private-secret'});
  else if (kind === 'invalidId') f.frame({...authenticated, account_public_id: '../other'});
  else if (kind === 'invalidTime') f.frame({...authenticated, checked_at: '2026-02-30T00:00:00Z'});
  else if (kind === 'duplicateKey') f.children[0].stdout.write('{"schema_version":"windows-platform-login-v1","state":"FAILED","state":"CANCELLED"}\n');
  else if (kind === 'invalidUtf8') f.children[0].stdout.write(Buffer.from([0xff, 10]));
  else if (kind === 'oversize') f.children[0].stdout.write('a'.repeat(16385));
  else if (kind === 'truncated') f.children[0].stdout.write(JSON.stringify(authenticated));
  else f.frame(authenticated);
  if (kind === 'duplicateTerminal') f.frame(authenticated);
  f.close(kind === 'exit' ? 1 : 0);
  expect(await outcome).toBe('SOURCE_HOST_FAILED'); await expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
});

it('accepts a bounded split UTF8 frame and safe failure before OPENED', async () => {
  const f = await fixture(); const run = f.driver.start({profileId}); await tick();
  const frame = Buffer.from(JSON.stringify({schema_version, state:'BLOCKED_INPUT', error_code:'PLATFORM_AUTH_REQUIRED'}) + '\n');
  f.children[0].stdout.write(frame.subarray(0, 12)); f.children[0].stdout.write(frame.subarray(12)); f.close();
  await expect(run.completed).rejects.toThrow('PLATFORM_AUTH_REQUIRED');
  await expect(run.opened).rejects.toThrow('PLATFORM_AUTH_REQUIRED'); await run.stop();
});

it('EOF cancellation keeps stop pending until close and discards late authentication', async () => {
  const f = await fixture(); const abort = new AbortController(); const run = f.driver.start({profileId, signal: abort.signal});
  const outcome = run.completed.catch(e => e.message); await tick(); abort.abort();
  let stopped = false; const stop = run.stop().then(() => {stopped = true;}); await tick();
  expect(f.children[0].stdin.writableEnded).toBe(true); expect(stopped).toBe(false);
  f.frame(opened); f.frame(authenticated); f.close(); await stop;
  expect(await outcome).toBe('PLATFORM_LOGIN_CANCELLED');
});

it('does not spawn when cancelled before its deferred startup', async () => {
  const f = await fixture(); const abort = new AbortController(); abort.abort();
  const run = f.driver.start({profileId, signal: abort.signal});
  await expect(run.completed).rejects.toThrow('PLATFORM_LOGIN_CANCELLED'); await run.stop(); expect(f.spawn).not.toHaveBeenCalled();
});

it.each(['forced','hostFailure','spawnError'])('never claims known stop after %s cleanup', async kind => {
  const f = await fixture(); const run = f.driver.start({profileId}); const outcome = run.completed.catch(e => e.message); await tick();
  if (kind === 'hostFailure') {f.frame({schema_version,state:'FAILED',error_code:'SOURCE_HOST_FAILED'}); f.close();}
  if (kind === 'spawnError') {f.children[0].emit('error', new Error('private launch path')); f.close(-2);}
  const stop = run.stop(); const assertion = expect(stop).rejects.toThrow('SOURCE_STOP_FAILED');
  if (kind === 'forced') {await vi.advanceTimersByTimeAsync(30000); expect(f.children[0].kill).toHaveBeenCalledOnce();}
  await assertion; expect(await outcome).toMatch(/^SOURCE_(HOST|STOP)_FAILED$/);
  f.close(); await expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
});

it('bounds total runtime at 180 seconds plus 30-second cleanup grace', async () => {
  const f = await fixture(); const run = f.driver.start({profileId}); const outcome = run.completed.catch(e => e.message); await tick();
  await vi.advanceTimersByTimeAsync(180000); expect(f.children[0].stdin.writableEnded).toBe(true);
  f.frame({schema_version,state:'CANCELLED',error_code:'PLATFORM_LOGIN_CANCELLED'}); f.close();
  expect(await outcome).toBe('PLATFORM_LOGIN_TIMED_OUT'); await run.stop();
});

it('a synchronous stop before creation and a thrown spawn have bounded safe outcomes', async () => {
  const f = await fixture(); const run = f.driver.start({profileId}); const stopped = run.stop();
  await expect(run.completed).rejects.toThrow('PLATFORM_LOGIN_CANCELLED'); await stopped; expect(f.spawn).not.toHaveBeenCalled();
  const g = await fixture(); g.spawn.mockImplementation(() => {throw new Error('private launch path');});
  const bad = g.driver.start({profileId}); await expect(bad.completed).rejects.toThrow('SOURCE_HOST_FAILED');
  await expect(bad.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
});

it('uses a fresh output UUID for every login run without changing the profile', async () => {
  const f = await fixture(); const paths: string[] = [];
  for (let i = 0; i < 2; i++) {
    const run = f.driver.start({profileId}); await tick();
    const request = JSON.parse(f.children[i].stdin.read().toString()); paths.push(request.output_path);
    expect(request.profile_path).toBe(f.options.profileRoot + '\\' + profileId);
    f.children[i].stdout.write(JSON.stringify({schema_version, state: 'CANCELLED'}) + '\n'); f.children[i].emit('close', 0, null);
    await expect(run.completed).rejects.toThrow('PLATFORM_LOGIN_CANCELLED'); await run.stop();
  }
  expect(paths[0]).not.toBe(paths[1]);
});

it.skipIf(process.platform !== 'win32').each(['success','cancel'])('actual Node to fixed Python host %s fixture (no browser or platform network)', async scenario => {
  vi.useRealTimers();
  const fs = await vi.importActual<typeof import('node:fs')>('node:fs');
  const {join, resolve} = await import('node:path');
  const {tmpdir} = await import('node:os');
  const {fileURLToPath} = await import('node:url');
  const realSpawn = (await import('node:child_process')).spawn;
  const project = fileURLToPath(new URL('../../', import.meta.url));
  const python = process.env.YIKE_PLATFORM_LOGIN_TEST_PYTHON ?? resolve(project, '../../.runtime/venvs/win-device-review/Scripts/python.exe');
  expect(fs.existsSync(python), 'Set YIKE_PLATFORM_LOGIN_TEST_PYTHON to the governed test interpreter').toBe(true);
  const root = fs.mkdtempSync(join(tmpdir(), 'yike-login-node-'));
  try {
    const cwd = join(root, 'project'); fs.mkdirSync(join(cwd, 'app'), {recursive:true});
    const runtimePath = join(root, 'runtime'), profileRoot = join(root, 'profiles'), outputRoot = join(root, 'outputs');
    for (const dir of [runtimePath,profileRoot,outputRoot]) fs.mkdirSync(dir);
    fs.writeFileSync(join(cwd, 'app/__init__.py'), `__path__.append(${JSON.stringify(join(project, 'app'))})\n`);
    // Real host parser/OPENED+terminal emitter/EOF watcher; replace only its
    // browser-supervisor boundary so this test never opens a platform session.
    fs.writeFileSync(join(cwd, 'app/windows_platform_login.py'), `
from pathlib import Path
import time
source = ${JSON.stringify(join(project, 'app/windows_platform_login.py'))}
namespace = {'__name__':'offline_host_fixture','__file__':source}
exec(compile(Path(source).read_text(encoding='utf-8'),source,'exec'),namespace)
def controlled_browser(**kwargs):
    kwargs['on_opened']()
    if ${JSON.stringify(scenario)} == 'cancel':
        deadline=time.monotonic()+5
        while not kwargs['cancel_requested']() and time.monotonic()<deadline: time.sleep(0.01)
        assert kwargs['cancel_requested']()
        return dict(schema_version='windows-platform-login-v1',state='CANCELLED',error_code='PLATFORM_LOGIN_CANCELLED')
    return dict(schema_version='windows-platform-login-v1',state='AUTHENTICATED',account_public_id='abc12345',checked_at='2026-09-10T01:02:03Z')
namespace['login_windows_platform']=controlled_browser
raise SystemExit(namespace['main']())
`);
    const {createPlatformLoginDriver} = await import('../src/main/platformLoginDriver');
    const driver = createPlatformLoginDriver({pythonExecutable:python, projectRoot:cwd, runtimePath, profileRoot, outputRoot, spawn:realSpawn});
    const run = driver.start({profileId});
    await run.opened;
    if (scenario === 'success') expect(await run.completed).toEqual({account_public_id:'abc12345',checked_at:authenticated.checked_at});
    else {
      const stop = run.stop(); await expect(run.completed).rejects.toThrow('PLATFORM_LOGIN_CANCELLED'); await stop;
    }
    await run.stop();
  } finally {fs.rmSync(root,{recursive:true,force:true});}
}, 15000);
