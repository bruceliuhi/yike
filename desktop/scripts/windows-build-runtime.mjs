import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {readFileSync, statSync} from 'node:fs';
import path from 'node:path';

export const REQUIRED_NODE_RANGE = '>=24.15.0 <25';
export class BuildRuntimeError extends Error {
  constructor(code) {super(code); this.code = code;}
}
export function isSupportedNodeVersion(version) {
  const parts = typeof version === 'string' && /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  return Boolean(parts && Number(parts[1]) === 24 && Number(parts[2]) >= 15);
}
function pathEntries(environment) {
  return Object.entries(environment).filter(([key]) => key.toLowerCase() === 'path')
    .flatMap(([, value]) => String(value).split(path.delimiter)).filter(Boolean)
    .map(value => value.startsWith('"') && value.endsWith('"') ? value.slice(1, -1) : value);
}
export function childEnvironment(nodeExecutable, environment = process.env) {
  const copy = Object.fromEntries(Object.entries(environment).filter(([key]) => key.toLowerCase() !== 'path'));
  const seen = new Set();
  const entries = [path.dirname(nodeExecutable), ...pathEntries(environment)].filter(value => {
    const key = process.platform === 'win32' ? value.toLowerCase() : value;
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
  copy.PATH = entries.join(path.delimiter);
  return copy;
}
function regularFile(file, code) {
  try {
    if (!statSync(file).isFile()) throw new BuildRuntimeError(code);
    return true;
  } catch (error) {
    if (['ENOENT', 'ENOTDIR'].includes(error.code)) return false;
    throw new BuildRuntimeError(code);
  }
}
function probe(nodeExecutable, args, env, cwd, code) {
  const result = spawnSync(nodeExecutable, args, {env, cwd, encoding: 'utf8', windowsHide: true, timeout: 15000, maxBuffer: 65536});
  const output = result.stdout?.trim();
  if (result.error || result.status !== 0 || !output || /[\x00-\x1f\x7f]/.test(output)) throw new BuildRuntimeError(code);
  return output;
}
export function createWindowsBuildRuntime({nodeExecutable = process.execPath, env = process.env, cwd = process.cwd()} = {}) {
  const environment = childEnvironment(nodeExecutable, env);
  let measured;
  try {
    measured = JSON.parse(probe(nodeExecutable, ['-p', 'JSON.stringify({version:process.versions.node,arch:process.arch})'], environment, cwd, 'NODE_RUNTIME_PROBE_FAILED'));
  } catch {throw new BuildRuntimeError('NODE_RUNTIME_PROBE_FAILED');}
  if (!isSupportedNodeVersion(measured.version) || measured.arch !== 'x64') throw new BuildRuntimeError('WINDOWS_X64_NODE24_15_REQUIRED');

  // Discover npm.cmd in the caller's original PATH order, but never execute its shell wrapper.
  const npmCmd = pathEntries(env).map(directory => path.resolve(cwd, directory, 'npm.cmd'))
    .find(file => regularFile(file, 'NPM_LAYOUT_PROBE_FAILED'));
  if (!npmCmd) throw new BuildRuntimeError('NPM_CMD_NOT_FOUND');
  const localBin = path.join(path.dirname(npmCmd), 'node_modules', 'npm', 'bin');
  const prefixScript = path.join(localBin, 'npm-prefix.js');
  if (!regularFile(prefixScript, 'NPM_PREFIX_PROBE_FAILED')) throw new BuildRuntimeError('NPM_PREFIX_PROBE_FAILED');
  const prefix = probe(nodeExecutable, [prefixScript], environment, cwd, 'NPM_PREFIX_PROBE_FAILED');
  if (!path.isAbsolute(prefix)) throw new BuildRuntimeError('NPM_PREFIX_PROBE_FAILED');
  const globalCli = path.join(prefix, 'node_modules', 'npm', 'bin', 'npm-cli.js');
  const globalExists = regularFile(globalCli, 'NPM_CLI_NOT_FOUND');
  const npmCli = globalExists ? globalCli : path.join(localBin, 'npm-cli.js');
  if (!regularFile(npmCli, 'NPM_CLI_NOT_FOUND')) throw new BuildRuntimeError('NPM_CLI_NOT_FOUND');
  const npmVersion = probe(nodeExecutable, [npmCli, '--version'], environment, cwd, 'NPM_VERSION_PROBE_FAILED');
  if (!/^\d+\.\d+\.\d+$/.test(npmVersion)) throw new BuildRuntimeError('NPM_VERSION_PROBE_FAILED');
  let nodeSha256, npmCliSha256;
  try {
    nodeSha256 = createHash('sha256').update(readFileSync(nodeExecutable)).digest('hex');
    npmCliSha256 = createHash('sha256').update(readFileSync(npmCli)).digest('hex');
  } catch {throw new BuildRuntimeError('RUNTIME_FINGERPRINT_FAILED');}
  return {nodeExecutable, npmCli, environment, nodeVersion: measured.version, npmVersion,
    npmSource: globalExists ? 'global-prefix' : 'adjacent-local', nodeSha256, npmCliSha256, launchMode: 'selected-node-direct-cli'};
}
export function runtimeSummary(runtime) {
  // Never spread the runtime: it also contains executable paths and a private environment copy.
  return {requiredNodeRange: REQUIRED_NODE_RANGE, npmVersion: runtime?.npmVersion ?? null, npmSource: runtime?.npmSource ?? null,
    nodeSha256: runtime?.nodeSha256 ?? null, npmCliSha256: runtime?.npmCliSha256 ?? null, launchMode: runtime?.launchMode ?? null};
}
export function runNode(runtime, args, cwd) {
  const result = spawnSync(runtime.nodeExecutable, args, {cwd, env: runtime.environment, stdio: 'inherit', windowsHide: true});
  return Number.isInteger(result.status) ? result.status : 1;
}
export function runNpm(runtime, args, cwd) {return runNode(runtime, [runtime.npmCli, ...args], cwd);}
