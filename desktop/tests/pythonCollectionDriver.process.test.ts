/** Real Node -> fixed Python module -> real host/mapper; source fixture only, no platform network. */
import {afterEach, expect, it} from 'vitest';
import {mkdtemp, mkdir, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createPythonCollectionDriver} from '../src/main/pythonCollectionDriver';
import type {CollectionDriver} from '../src/main/collectionWorker';

const python = process.env.YIKE_SOURCE_HOST_PYTHON;
const realProcessTest = it.skipIf(process.platform !== 'win32' || !python);
const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const temporary: string[] = [];
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

afterEach(async () => {
  for (const directory of temporary.splice(0)) {
    if (dirname(resolve(directory)) !== resolve(tmpdir()) || !directory.includes('yike-source-host-'))
      throw new Error('Refusing unsafe fixture cleanup');
    await rm(directory, {recursive: true, force: true});
  }
});

async function fixture(cancel: boolean) {
  const projectRoot = await mkdtemp(join(tmpdir(), 'yike-source-host-'));
  temporary.push(projectRoot);
  await mkdir(join(projectRoot, 'app'));
  await writeFile(join(projectRoot, 'app/__init__.py'),
    `__path__.append(${JSON.stringify(join(repository, 'app'))})\n`);
  // Only the source boundary is substituted. The fixed -m entrypoint loads
  // current product host bytes and its real candidate mapper and validators.
  await writeFile(join(projectRoot, 'app/windows_collection_host.py'), `
import importlib.util, os, sys, time
from pathlib import Path
sys.path.insert(0, ${JSON.stringify(repository)})
spec = importlib.util.spec_from_file_location('_product_source_host', ${JSON.stringify(join(repository, 'app/windows_collection_host.py'))})
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
from tests.test_candidate_mapping import raw
marker = Path(${JSON.stringify(join(projectRoot, 'state'))})
release = Path(${JSON.stringify(join(projectRoot, 'release'))})
def source(**kwargs):
    print('private source diagnostic')
    print('private source stderr', file=sys.stderr)
    marker.write_text('started')
    if ${cancel ? 'True' : 'False'}:
        deadline = time.monotonic() + 8
        while not kwargs['cancel_requested']():
            if time.monotonic() > deadline: raise RuntimeError('fixture stop not requested')
            time.sleep(.005)
        marker.write_text('cancelling')
        while not release.exists():
            if time.monotonic() > deadline: raise RuntimeError('fixture cleanup not released')
            time.sleep(.005)
        marker.write_text('cleaned')
        return {'state': 'CANCELLED', 'task_completed': False}
    return {'state': 'COLLECTED', 'records': [raw('BILIBILI')], 'query': kwargs['query'],
            'collector_version': 'controlled-host-v1', 'task_completed': False}
host.collect_windows_source = source
raise SystemExit(host.main())
`, 'utf8');
  const target = {platform: 'BILIBILI' as const, access_mode: 'PLATFORM_ACCOUNT' as const,
    connection_id: id(5), connection_version: 1};
  const input: Parameters<CollectionDriver['start']>[0] = {
    snapshot: {profile_version_id: id(3), strategy_version_id: id(4), platforms: ['BILIBILI'],
      max_records: 2, max_runtime_seconds: 60,
      configuration: {schema_version: 'research-strategy-v1', name: '实际管道', source: 'search',
        keywords: ['设备'], exclusions: [], links: [], mode: 'once', schedule: null, research: null}},
    target, lease: {schema_version: 'execution-runtime-v1', operation: 'CLAIM', request_id: id(1),
      task_id: id(6), run_id: id(7), platform_run_id: id(8), status: 'RUNNING', stop_confirmed: false,
      lease_id: id(9), execution_generation: 1,
      lease_expires_at: new Date(Date.now() + 120000).toISOString(),
      deadline_at: new Date(Date.now() + 300000).toISOString()},
    maxRecords: 2, signal: new AbortController().signal,
  };
  const driver = createPythonCollectionDriver({pythonExecutable: python!, projectRoot,
    runtimePath: join(projectRoot, 'runtime'), profilePath: join(projectRoot, 'profile'),
    outputRoot: join(projectRoot, 'output'), binding: {deviceId: id(2), credentialVersion: 1, ...target}});
  const state = async () => readFile(join(projectRoot, 'state'), 'utf8').catch(() => '');
  const release = () => writeFile(join(projectRoot, 'release'), 'cleanup may finish');
  return {driver, input, state, release};
}

realProcessTest('real fixed module maps untouched source evidence and Node consumes formal records', async () => {
  const f = await fixture(false);
  const run = f.driver.start(f.input);
  try {
    const records = await run.completed;
    if(!Array.isArray(records))throw new Error('legacy array expected');
    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({kind: 'COMMENT', external_source_id: '101', external_comment_id: '202',
      public_url: 'https://www.bilibili.com/video/av101#reply202', title: ' 原标题 ',
      body: ' \t原文 e\u0301 / é\r\n需要设备🧰\t ', query: '设备', collector_version: 'controlled-host-v1',
      normalizer_version: 'raw-comment-candidate-v1', observed_at: '2026-09-09T02:00:00Z',
      published_at: '2026-09-08T01:02:03Z'});
    expect(JSON.stringify(records)).not.toContain('private source');
    expect(await f.state()).toBe('started');
  } finally {await run.stop();}
}, 15000);

realProcessTest('real stdin EOF cancellation waits for cleanup and host close before stop resolves', async () => {
  const f = await fixture(true);
  const run = f.driver.start(f.input);
  const outcome = run.completed.catch(error => error.message);
  let stopped = false;
  let stop: Promise<void> | undefined;
  try {
    await expect.poll(f.state, {timeout: 5000}).toBe('started');
    stop = run.stop().then(() => {stopped = true;});
    await expect.poll(f.state, {timeout: 5000}).toBe('cancelling');
    expect(stopped).toBe(false);
    await f.release();
    await stop;
    expect(await f.state()).toBe('cleaned');
    expect(stopped).toBe(true);
    expect(await outcome).toBe('SOURCE_DRIVER_CANCELLED');
  } finally {
    await f.release();
    await (stop ?? run.stop());
  }
}, 15000);
