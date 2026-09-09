import {afterEach, describe, expect, it} from 'vitest';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {copyFileSync, linkSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  REQUIRED_NODE_RANGE, childEnvironment, createWindowsBuildRuntime, isSupportedNodeVersion, runNpm, runtimeSummary
} from '../scripts/windows-build-runtime.mjs';
import {createEvidence, recordRuntime} from '../scripts/windows-build-evidence.mjs';

const roots = [];
const temporaryParent = realpathSync(os.tmpdir());
// These fixtures copy the current Node binary; they cannot supply an x64 binary on ARM.
const supportsRuntimeFixture = (arch = process.arch) => arch === 'x64';
const supportsBuildFixture = (platform = process.platform, arch = process.arch, machine = os.machine()) =>
  platform === 'win32' && supportsRuntimeFixture(arch) && ['x86_64', 'amd64', 'x64'].includes(machine.toLowerCase());
const digest = file => createHash('sha256').update(readFileSync(file)).digest('hex');
function put(file, content) {mkdirSync(path.dirname(file), {recursive: true}); writeFileSync(file, content);}
function fixture() {
  const root = mkdtempSync(path.join(temporaryParent, 'yike-runtime-test-'));
  roots.push(root);
  const node = path.join(root, 'selected node with spaces', path.basename(process.execPath));
  mkdirSync(path.dirname(node));
  try {linkSync(process.execPath, node);} catch {copyFileSync(process.execPath, node);}
  const npmDirectory = path.join(root, 'npm installation with spaces');
  const globalPrefix = path.join(root, 'global prefix with spaces');
  const localCli = path.join(npmDirectory, 'node_modules', 'npm', 'bin', 'npm-cli.js');
  const globalCli = path.join(globalPrefix, 'node_modules', 'npm', 'bin', 'npm-cli.js');
  const prefixScript = path.join(path.dirname(localCli), 'npm-prefix.js');
  const prefixCapture = path.join(root, 'prefix-called.json');
  // Discovery marker only. The runtime must never execute this npm.cmd file.
  put(path.join(npmDirectory, 'npm.cmd'), 'THIS DISCOVERY MARKER MUST NEVER RUN');
  put(prefixScript, `require('node:fs').writeFileSync(${JSON.stringify(prefixCapture)}, JSON.stringify({node:process.execPath,version:process.versions.node})); console.log(${JSON.stringify(globalPrefix)});`);
  const cli = mode => `const {spawnSync}=require('node:child_process'); const fs=require('node:fs');
if(process.argv[2]==='--version'){console.log('${mode === 'global-prefix' ? '11.6.2' : '10.8.2'}');}
else {const child=spawnSync('node',['-p','JSON.stringify({node:process.execPath,version:process.versions.node})'],{encoding:'utf8'});
if(child.status!==0)process.exit(83); fs.writeFileSync(process.argv[3],JSON.stringify({mode:'${mode}',node:process.execPath,
version:process.versions.node,arguments:process.argv.slice(4),child:JSON.parse(child.stdout)})); process.exit(37);}`;
  put(localCli, cli('adjacent-local'));
  put(globalCli, cli('global-prefix'));
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => key.toLowerCase() !== 'path'));
  env.Path = path.dirname(process.execPath);
  env.PATH = npmDirectory;
  env.PRIVATE_BUILD_TOKEN = 'never-save-this-secret';
  return {root, node, env, npmDirectory, globalPrefix, localCli, globalCli, prefixScript, prefixCapture};
}
const discover = value => createWindowsBuildRuntime({nodeExecutable: value.node, env: value.env, cwd: value.root});
afterEach(() => {
  for (const root of roots.splice(0)) {
    if (!path.isAbsolute(root) || path.dirname(root) !== temporaryParent || !path.basename(root).startsWith('yike-runtime-test-') ||
      realpathSync(root).toLowerCase() !== path.resolve(root).toLowerCase()) throw new Error('Unsafe runtime fixture cleanup');
    // Windows can briefly retain the executable image after the npm lifecycle child exits.
    rmSync(root, {recursive: true, force: true, maxRetries: 5, retryDelay: 100});
  }
});

describe('Windows build runtime', () => {
  it.each([
    ['darwin', 'arm64', 'arm64', false, false],
    ['darwin', 'x64', 'x86_64', true, false],
    ['win32', 'arm64', 'ARM64', false, false],
    ['win32', 'x64', 'ARM64', true, false],
    ['win32', 'ia32', 'x86_64', false, false],
    ['win32', 'x64', 'x86_64', true, true],
    ['win32', 'x64', 'AMD64', true, true],
    ['linux', 'x64', 'x86_64', true, false],
  ])('selects real fixture coverage for %s / %s / %s', (platform, arch, machine, runtime, build) => {
    expect(supportsRuntimeFixture(arch)).toBe(runtime);
    expect(supportsBuildFixture(platform, arch, machine)).toBe(build);
  });

  it.skipIf(process.arch === 'x64')('rejects the real non-x64 Node before npm discovery', () => {
    expect(isSupportedNodeVersion(process.versions.node)).toBe(true);
    expect(() => createWindowsBuildRuntime({env: {}, cwd: temporaryParent})).toThrow('WINDOWS_X64_NODE24_15_REQUIRED');
  });

  it.each([['24.11.1', false], ['24.14.99', false], ['24.15.0', true], ['24.19.0', true], ['25.0.0', false],
    ['24.15.0-rc.1', false], ['24.15', false], ['24.15.0\nsecret', false]])('validates the minimum Node range for %s', (version, valid) => {
    expect(isSupportedNodeVersion(version)).toBe(valid);
  });

  it('keeps package and lock root engines consistent with the runtime range', () => {
    expect(REQUIRED_NODE_RANGE).toBe('>=24.15.0 <25');
    expect(JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).engines.node).toBe(REQUIRED_NODE_RANGE);
    expect(JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8')).packages[''].engines.node).toBe(REQUIRED_NODE_RANGE);
  });

  it('merges Path and PATH without changing the original environment', () => {
    const fixtureNode = path.join(temporaryParent, 'selected node', 'node.exe');
    const input = {Path: ['first', 'shared'].join(path.delimiter), PATH: ['shared', 'last'].join(path.delimiter), KEEP: 'yes'};
    const snapshot = {...input};
    const actual = childEnvironment(fixtureNode, input);
    expect(input).toEqual(snapshot);
    expect(Object.keys(actual).filter(key => key.toLowerCase() === 'path')).toEqual(['PATH']);
    expect(actual.PATH.split(path.delimiter)).toEqual([path.dirname(fixtureNode), 'first', 'shared', 'last']);
    expect(actual.KEEP).toBe('yes');
  });

  it.skipIf(!supportsRuntimeFixture()).each(['global-prefix', 'adjacent-local'])('runs the real discovered %s CLI and its node child with the selected spaced Node path, preserving exit 37', mode => {
    const value = fixture();
    if (mode === 'adjacent-local') rmSync(value.globalCli);
    const runtime = discover(value);
    const marker = path.join(value.root, 'result with spaces.json');
    expect(runNpm(runtime, ['fixture', marker, 'argument with spaces', '&literal'], value.root)).toBe(37);
    const result = JSON.parse(readFileSync(marker, 'utf8'));
    expect(result).toMatchObject({mode, node: value.node, version: process.versions.node,
      arguments: ['argument with spaces', '&literal'], child: {node: value.node, version: process.versions.node}});
    expect(JSON.parse(readFileSync(value.prefixCapture, 'utf8'))).toEqual({node: value.node, version: process.versions.node});
    expect(runtimeSummary(runtime)).toMatchObject({requiredNodeRange: REQUIRED_NODE_RANGE, npmSource: mode,
      npmVersion: mode === 'global-prefix' ? '11.6.2' : '10.8.2', nodeSha256: digest(value.node),
      npmCliSha256: digest(mode === 'global-prefix' ? value.globalCli : value.localCli), launchMode: 'selected-node-direct-cli'});
  });

  it.skipIf(!supportsRuntimeFixture()).each(['missing-prefix', 'prefix-exit', 'prefix-empty', 'prefix-lines', 'prefix-relative', 'missing-cli', 'bad-version', 'global-version-exit'])('fails closed on %s without using a lower-priority CLI', failure => {
    const value = fixture();
    let expected = 'NPM_PREFIX_PROBE_FAILED';
    if (failure === 'missing-prefix') rmSync(value.prefixScript);
    if (failure === 'prefix-exit') put(value.prefixScript, 'process.exit(37);');
    if (failure === 'prefix-empty') put(value.prefixScript, 'console.log("");');
    if (failure === 'prefix-lines') put(value.prefixScript, 'console.log("C:/one\\nC:/two");');
    if (failure === 'prefix-relative') put(value.prefixScript, 'console.log("relative-prefix");');
    if (failure === 'missing-cli') {rmSync(value.globalCli); rmSync(value.localCli); expected = 'NPM_CLI_NOT_FOUND';}
    if (failure === 'bad-version') {put(value.globalCli, 'console.log("11.6.2\\nsecret");'); expected = 'NPM_VERSION_PROBE_FAILED';}
    if (failure === 'global-version-exit') {put(value.globalCli, 'process.exit(37);'); expected = 'NPM_VERSION_PROBE_FAILED';}
    expect(() => discover(value)).toThrow(expected);
  });

  it.skipIf(!supportsRuntimeFixture())('serializes only the runtime whitelist into build evidence', () => {
    const value = fixture();
    const runtime = discover(value);
    runtime.extraPath = value.root;
    runtime.EXTRA_SECRET = 'must-not-appear';
    const evidence = createEvidence(value.root);
    recordRuntime(evidence, runtime);
    const report = JSON.parse(readFileSync(path.join(evidence.directory, 'windows-build.json'), 'utf8'));
    expect(Object.keys(report.runtime).sort()).toEqual(['launchMode', 'nodeSha256', 'npmCliSha256', 'npmSource', 'npmVersion', 'requiredNodeRange']);
    expect(JSON.stringify(report)).not.toContain(value.root);
    expect(JSON.stringify(report)).not.toContain(value.node);
    expect(JSON.stringify(report)).not.toMatch(/never-save-this-secret|must-not-appear|extraPath|environment/);
  });

  it.skipIf(!supportsBuildFixture()).each(['dependency-exit', 'version-probe-exit'])('records the actual %s failure stage without running later commands', failure => {
    const value = fixture();
    const calls = path.join(value.root, 'cli-calls.json');
    put(value.globalCli, failure === 'version-probe-exit' ? 'process.exit(37);' :
      `if(process.argv[2]==='--version')console.log('11.6.2'); else {require('node:fs').writeFileSync(${JSON.stringify(calls)},JSON.stringify(process.argv.slice(2)));process.exit(37);}`);
    const module = new URL('../scripts/windows-build-evidence.mjs', import.meta.url).href;
    const result = spawnSync(value.node, ['--input-type=module', '-e',
      `import {runWindowsBuild} from ${JSON.stringify(module)}; process.exitCode=runWindowsBuild(${JSON.stringify(value.root)});`],
    {env: value.env, cwd: value.root, encoding: 'utf8', windowsHide: true, timeout: 15000});
    expect(result.status, result.stderr).toBe(1);
    const directory = path.join(value.root, 'out', 'windows-evidence');
    const report = JSON.parse(readFileSync(path.join(directory, readdirSync(directory)[0], 'windows-build.json'), 'utf8'));
    expect(report.outcome).toBe('BUILD_FAILED');
    expect(report.artifacts).toEqual([]);
    if (failure === 'dependency-exit') {
      expect(report.failureCode).toBe('STAGE_FAILED');
      expect(report.stages[0].status).toBe('PASSED');
      expect(report.stages[1]).toMatchObject({status: 'FAILED', exitCode: 37});
      expect(report.stages.slice(2).every(stage => stage.status === 'NOT_RUN')).toBe(true);
      expect(JSON.parse(readFileSync(calls, 'utf8'))).toEqual(['ci']);
      expect(report.runtime.npmSource).toBe('global-prefix');
    } else {
      expect(report.failureCode).toBe('NPM_VERSION_PROBE_FAILED');
      expect(report.stages[0].status).toBe('FAILED');
      expect(report.stages.slice(1).every(stage => stage.status === 'NOT_RUN')).toBe(true);
      expect(report.runtime.npmVersion).toBeNull();
    }
    expect(JSON.stringify(report)).not.toContain(value.root);
    expect(JSON.stringify(report)).not.toContain('never-save-this-secret');
  });

  it.skipIf(process.platform !== 'win32' || !supportsRuntimeFixture())('executes the installed npm CLI lifecycle using the selected Node rather than the older system Node', () => {
    const value = fixture();
    const project = path.join(value.root, 'real npm project with spaces');
    put(path.join(project, 'package.json'), JSON.stringify({name: 'runtime-fixture', private: true, scripts: {probe: 'node child.cjs'}}));
    put(path.join(project, 'child.cjs'), `const {spawnSync}=require('node:child_process'); const child=spawnSync('node',['-p','process.execPath'],{encoding:'utf8'});
require('node:fs').writeFileSync('lifecycle.json',JSON.stringify({node:process.execPath,version:process.versions.node,childNode:child.stdout.trim(),npmNode:process.env.npm_node_execpath})); process.exit(37);`);
    const runtime = createWindowsBuildRuntime({nodeExecutable: value.node, env: process.env, cwd: project});
    expect(runNpm(runtime, ['run', 'probe', '--silent'], project)).toBe(37);
    expect(JSON.parse(readFileSync(path.join(project, 'lifecycle.json'), 'utf8'))).toEqual({node: value.node, version: process.versions.node,
      childNode: value.node, npmNode: value.node});
  });
});
