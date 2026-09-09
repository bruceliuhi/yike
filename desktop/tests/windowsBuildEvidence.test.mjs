import {afterEach, describe, expect, it} from 'vitest';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  addArtifact, beginStage, createEvidence, endStage, finishEvidence, sha256
} from '../scripts/windows-build-evidence.mjs';

const roots = [];
function fixture() {
  const root = mkdtempSync(path.join(os.tmpdir(), 'yike-windows-evidence-test-'));
  roots.push(root);
  writeFileSync(path.join(root, 'package-lock.json'), 'test-lock\n');
  return root;
}
function saved(evidence) {
  return JSON.parse(readFileSync(path.join(evidence.directory, 'windows-build.json'), 'utf8'));
}
function complete(evidence, id, code = 0) {
  beginStage(evidence, id);
  endStage(evidence, id, code);
}
afterEach(() => roots.splice(0).forEach(root => rmSync(root, {recursive: true, force: true})));

describe('Windows build evidence', () => {
  it('records measured host and lock hash without environment values or unearned success', () => {
    const root = fixture();
    const evidence = createEvidence(root);
    const report = saved(evidence);
    expect(report.host).toMatchObject({platform: process.platform, nodeVersion: process.version,
      nodeArch: process.arch, osArch: os.machine(), osVersion: os.version()});
    expect(report.source.lockfile.sha256).toBe(createHash('sha256').update('test-lock\n').digest('hex'));
    expect(report.source).toMatchObject({gitAvailable: false, commit: null, dirty: null});
    expect(report.outcome).toBe('IN_PROGRESS');
    expect(report.manualAcceptance).toBe('UNTESTED');
    expect(report.stages).toHaveLength(9);
    expect(report.stages.every(stage => stage.status === 'NOT_RUN' && stage.exitCode === null)).toBe(true);
    expect(Object.keys(report.host).sort()).toEqual(['nodeArch','nodeVersion','osArch','osRelease','osVersion','platform']);
    expect(JSON.stringify(report)).not.toMatch(/process\.env|HOME|TOKEN|password|username|hostname/);
    const manual = readFileSync(path.join(evidence.directory, 'WINDOWS_ACCEPTANCE.md'), 'utf8');
    expect(manual).toContain(report.runId);
    expect(manual).not.toContain('{{RUN_ID}}');
    expect(manual.match(/\| UNTESTED \|/g)).toHaveLength(11);
  });

  it('persists stage failure with its actual exit code and leaves later stages unexecuted', () => {
    const evidence = createEvidence(fixture());
    complete(evidence, 'preflight');
    beginStage(evidence, 'dependencies');
    expect(saved(evidence).stages[1]).toMatchObject({status: 'RUNNING', exitCode: null});
    endStage(evidence, 'dependencies', 17);
    expect(finishEvidence(evidence, 'STAGE_FAILED')).toBe(1);
    const report = saved(evidence);
    expect(report).toMatchObject({outcome: 'BUILD_FAILED', failureCode: 'STAGE_FAILED', manualAcceptance: 'UNTESTED'});
    expect(report.finishedAt).toEqual(expect.any(String));
    expect(report.stages[1]).toMatchObject({status: 'FAILED', exitCode: 17});
    expect(report.stages.slice(2).every(stage => stage.status === 'NOT_RUN' && stage.exitCode === null)).toBe(true);
    expect(report.artifacts).toEqual([]);
  });

  it('hashes actual output bytes and rejects paths outside out including symlink escapes', () => {
    const root = fixture();
    const evidence = createEvidence(root);
    const artifact = path.join(root, 'out', 'fixture.exe');
    const content = Buffer.from([0, 1, 240, 128, 10]);
    writeFileSync(artifact, content);
    addArtifact(evidence, 'out/fixture.exe');
    expect(saved(evidence).artifacts).toEqual([{
      path: 'out/fixture.exe', bytes: content.length,
      sha256: createHash('sha256').update(content).digest('hex'), modifiedAt: expect.any(String)
    }]);
    expect(sha256(artifact)).toBe(saved(evidence).artifacts[0].sha256);
    expect(() => addArtifact(evidence, '../package-lock.json')).toThrow('INVALID_ARTIFACT_PATH');
    expect(() => addArtifact(evidence, 'package-lock.json')).toThrow('INVALID_ARTIFACT_PATH');
    expect(() => addArtifact(evidence, artifact)).toThrow('INVALID_ARTIFACT_PATH');
    // Windows symlink creation may require extra privileges; never require those for a build test.
    if (process.platform !== 'win32') {
      symlinkSync(path.join(root, 'package-lock.json'), path.join(root, 'out', 'escaped.exe'));
      expect(() => addArtifact(evidence, 'out/escaped.exe')).toThrow('INVALID_ARTIFACT_PATH');
    }
  });

  it('does not let partial or explicit failed runs become successful', () => {
    const evidence = createEvidence(fixture());
    complete(evidence, 'preflight');
    expect(finishEvidence(evidence)).toBe(1);
    expect(saved(evidence).failureCode).toBe('INCOMPLETE_BUILD');
    const other = createEvidence(fixture());
    for (const stage of other.report.stages) complete(other, stage.id);
    expect(finishEvidence(other, 'SCRIPT_FAILED')).toBe(1);
    expect(saved(other).outcome).toBe('BUILD_FAILED');
  });

  it('keeps human checks UNTESTED even when every automatic stage succeeds', () => {
    const evidence = createEvidence(fixture());
    for (const stage of evidence.report.stages) complete(evidence, stage.id);
    expect(finishEvidence(evidence)).toBe(0);
    expect(saved(evidence)).toMatchObject({outcome: 'BUILD_SUCCEEDED', failureCode: null, manualAcceptance: 'UNTESTED'});
    expect(saved(evidence).stages.every(stage => stage.exitCode === 0)).toBe(true);
    expect(readFileSync(path.join(evidence.directory, 'WINDOWS_ACCEPTANCE.md'), 'utf8')).toContain('整体人工结论：**UNTESTED**');
  });

  it('records real Git commit and dirty state without recording changed file names', () => {
    const root = fixture();
    const git = args => {
      const result = spawnSync('git', args, {cwd: root, encoding: 'utf8'});
      expect(result.status, result.stderr).toBe(0);
      return result.stdout.trim();
    };
    git(['init', '-q']);
    git(['add', 'package-lock.json']);
    git(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=.', 'commit', '-qm', 'fixture']);
    const commit = git(['rev-parse', 'HEAD']);
    // Use a separate evidence output, so generated reports do not dirty this fixture repository.
    const outside = fixture();
    const clean = createEvidence(root, path.join(outside, 'clean'));
    expect(saved(clean).source).toMatchObject({commit, dirty: false, gitAvailable: true});
    writeFileSync(path.join(root, 'private-file-name.txt'), 'do not record this content');
    const dirty = createEvidence(root, path.join(outside, 'dirty'));
    expect(saved(dirty).source).toMatchObject({commit, dirty: true, gitAvailable: true});
    expect(JSON.stringify(saved(dirty))).not.toContain('private-file-name');
    expect(JSON.stringify(saved(dirty))).not.toContain('do not record');
  });

  it('rejects out-of-order and duplicate stage completions', () => {
    const evidence = createEvidence(fixture());
    expect(() => endStage(evidence, 'preflight', 0)).toThrow('INVALID_STAGE');
    expect(() => beginStage(evidence, 'unknown')).toThrow('INVALID_STAGE');
    complete(evidence, 'preflight');
    expect(() => beginStage(evidence, 'preflight')).toThrow('INVALID_STAGE');
    expect(() => endStage(evidence, 'preflight', 0)).toThrow('INVALID_STAGE');
  });
});
