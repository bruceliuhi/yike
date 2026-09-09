import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {lstatSync, readFileSync, readdirSync, realpathSync} from 'node:fs';
import path from 'node:path';

export class SourceBindingError extends Error {constructor(code) {super(code); this.code = code;}}
const digest = value => createHash('sha256').update(value).digest('hex');
export const isCommit = value => typeof value === 'string' && /^[a-f0-9]{40}$/i.test(value);
function git(root, args, input) {
  const result = spawnSync('git', args, {cwd: root, input, windowsHide: true, maxBuffer: 128 * 1024 * 1024});
  if (result.error || result.status !== 0) throw new SourceBindingError('SOURCE_GIT_UNAVAILABLE');
  return result.stdout;
}
function scan(directory, output = []) {
  for (const entry of readdirSync(directory, {withFileTypes: true})) {
    const file = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new SourceBindingError('SOURCE_UNTRACKED_OR_LINKED_INPUT');
    if (entry.isDirectory()) scan(file, output);
    else if (entry.isFile()) output.push(file);
    else throw new SourceBindingError('SOURCE_UNTRACKED_OR_LINKED_INPUT');
  }
  return output;
}
/** Byte equality is deliberate: use a clean checkout with core.autocrlf=false. */
export function captureSource(root, expectedCommit) {
  if (!isCommit(expectedCommit)) throw new SourceBindingError('EXPECTED_COMMIT_REQUIRED');
  expectedCommit = expectedCommit.toLowerCase();
  root = realpathSync(path.resolve(root));
  const repository = git(root, ['rev-parse', '--show-toplevel']).toString().trim();
  const commit = git(root, ['rev-parse', 'HEAD']).toString().trim();
  if (commit !== expectedCommit) throw new SourceBindingError('SOURCE_COMMIT_MISMATCH');
  if (git(root, ['status', '--porcelain=v1', '--untracked-files=normal']).toString().trim()) throw new SourceBindingError('SOURCE_DIRTY');
  const prefix = path.relative(repository, root).split(path.sep).join('/');
  const listing = git(repository, ['ls-tree', '-rz', '--full-tree', expectedCommit, '--', prefix || '.']).toString();
  const entries = listing.split('\0').filter(Boolean).map(line => {
    const match = /^(100644|100755) blob ([a-f0-9]{40})\t(.+)$/.exec(line);
    if (!match) throw new SourceBindingError('SOURCE_UNSUPPORTED_ENTRY');
    return {oid: match[2], path: match[3]};
  });
  if (!entries.length) throw new SourceBindingError('SOURCE_EMPTY');
  // One Git process avoids spawning hundreds of processes on Windows.
  const blobs = git(repository, ['cat-file', '--batch'], entries.map(x => x.oid).join('\n') + '\n');
  let offset = 0;
  const inputs = entries.map(entry => {
    const end = blobs.indexOf(10, offset);
    const header = /^([a-f0-9]{40}) blob (\d+)$/.exec(blobs.subarray(offset, end).toString());
    if (!header || header[1] !== entry.oid) throw new SourceBindingError('SOURCE_BLOB_INVALID');
    const size = Number(header[2]);
    const content = blobs.subarray(end + 1, end + 1 + size); offset = end + 2 + size;
    const file = path.join(repository, ...entry.path.split('/'));
    let actual;
    try {
      if (!lstatSync(file).isFile()) throw new Error();
      actual = readFileSync(file);
    } catch {throw new SourceBindingError('SOURCE_INPUT_MISSING_OR_LINKED');}
    if (!actual.equals(content)) throw new SourceBindingError('SOURCE_INPUT_BYTES_MISMATCH');
    return {path: entry.path, bytes: actual.length, sha256: digest(actual)};
  });
  // Ignored local files under executable/build input directories must not silently enter Vite/Forge.
  const fileKey = file => process.platform === 'win32' ? file.toLowerCase() : file;
  const tracked = new Set(inputs.map(x => fileKey(path.resolve(repository, ...x.path.split('/')))));
  for (const name of ['src', 'build', 'assets', 'scripts']) {
    const directory = path.join(root, name);
    let stat;
    try {stat = lstatSync(directory);} catch (error) {if (error.code === 'ENOENT') continue; throw error;}
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new SourceBindingError('SOURCE_UNTRACKED_OR_LINKED_INPUT');
    for (const file of scan(directory)) if (!tracked.has(fileKey(file))) throw new SourceBindingError('SOURCE_UNTRACKED_OR_LINKED_INPUT');
  }
  return {commit, inputCount: inputs.length, manifestSha256: digest(JSON.stringify(inputs)), inputs};
}
export function assertSameSource(before, after) {
  if (!before || !after || before.commit !== after.commit || before.manifestSha256 !== after.manifestSha256) throw new SourceBindingError('SOURCE_CHANGED_DURING_BUILD');
}

/** Keep counts and repository-relative test names, never logs, failure messages or absolute paths. */
export function summarizeTests(report, root) {
  const names = ['numTotalTests', 'numPassedTests', 'numFailedTests', 'numPendingTests', 'numTodoTests'];
  if (!report || !names.every(key => Number.isSafeInteger(report[key] ?? (key === 'numTodoTests' ? 0 : undefined)) && (report[key] ?? 0) >= 0) || !Array.isArray(report.testResults)) throw new Error('TEST_SUMMARY_INVALID');
  const counts = {total: report.numTotalTests, passed: report.numPassedTests, failed: report.numFailedTests, skipped: report.numPendingTests, todo: report.numTodoTests ?? 0};
  if (counts.total === 0 || counts.total !== counts.passed + counts.failed + counts.skipped + counts.todo) throw new Error('TEST_SUMMARY_INVALID');
  const skipped = [];
  for (const suite of report.testResults) {
    const relative = typeof suite.name === 'string' ? path.relative(root, suite.name).split(path.sep).join('/') : '';
    if (!relative || relative.startsWith('../') || path.isAbsolute(relative) || !relative.startsWith('tests/')) throw new Error('TEST_SUMMARY_INVALID');
    for (const result of suite.assertionResults ?? []) if (['pending', 'skipped', 'todo', 'disabled'].includes(result.status)) {
      // Names can contain fixture inputs; the receiving reviewer uses the source file to inspect conditions.
      skipped.push({file: relative, index: skipped.filter(x => x.file === relative).length + 1, status: result.status, reason: 'Inspect platform/architecture/fixture condition in the bound source; not executed.'});
    }
  }
  return {...counts, files: report.testResults.length, skippedCases: skipped};
}
