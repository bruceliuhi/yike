import {afterEach, describe, expect, it} from 'vitest';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {captureSource, assertSameSource, summarizeTests} from '../scripts/windows-source-binding.mjs';
import {createEvidence, verifySourceBefore, verifySourceAfter, finishEvidence, beginStage, endStage} from '../scripts/windows-build-evidence.mjs';
const roots=[];
const git=(root,...args)=>{
  const run=spawnSync('git',args,{cwd:root,encoding:'utf8'});
  expect(run.status,run.stderr).toBe(0);return run.stdout.trim();
};
function fixture() {
  const root=mkdtempSync(path.join(os.tmpdir(),'yike-source-binding-'));roots.push(root);
  mkdirSync(path.join(root,'desktop/src'),{recursive:true});
  writeFileSync(path.join(root,'.gitignore'),'desktop/out/\ndesktop/src/ignored.ts\n');
  writeFileSync(path.join(root,'desktop/package-lock.json'),'{}\n');
  writeFileSync(path.join(root,'desktop/src/main.ts'),'export const value=1;\n');
  git(root,'init','-q');git(root,'config','core.autocrlf','false');git(root,'add','.');
  git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=.','commit','-qm','fixture');
  return {repository:root,root:path.join(root,'desktop'),commit:git(root,'rev-parse','HEAD')};
}
afterEach(()=>roots.splice(0).forEach(root=>rmSync(root,{recursive:true,force:true})));
describe('Windows exact candidate binding',()=>{
  it('captures real committed input bytes and identical final snapshot',()=>{
    const {root,commit}=fixture();const before=captureSource(root,commit);
    expect(before).toMatchObject({commit,inputCount:2});
    expect(before.inputs.map(x=>x.path)).toEqual(['desktop/package-lock.json','desktop/src/main.ts']);
    expect(()=>assertSameSource(before,captureSource(root,commit))).not.toThrow();
    expect(JSON.stringify(before)).not.toContain(root);
  });
  it.each([undefined,'main','abc','f'.repeat(39),'f'.repeat(41)])('requires a full immutable commit (%s)',expected=>{
    const {root}=fixture();expect(()=>captureSource(root,expected)).toThrow('EXPECTED_COMMIT_REQUIRED');
  });
  it('rejects a different candidate and dirty tracked or untracked inputs',()=>{
    const {root,commit}=fixture();expect(()=>captureSource(root,'f'.repeat(40))).toThrow('SOURCE_COMMIT_MISMATCH');
    writeFileSync(path.join(root,'extra.ts'),'private text');expect(()=>captureSource(root,commit)).toThrow('SOURCE_DIRTY');
    rmSync(path.join(root,'extra.ts'));writeFileSync(path.join(root,'src/main.ts'),'changed');
    expect(()=>captureSource(root,commit)).toThrow('SOURCE_DIRTY');
  });
  it('rejects ignored executable inputs even though Git is clean',()=>{
    const {root,commit}=fixture();writeFileSync(path.join(root,'src/ignored.ts'),'ignored');
    expect(()=>captureSource(root,commit)).toThrow('SOURCE_UNTRACKED_OR_LINKED_INPUT');
  });
  it('does not trust a clean status when checkout bytes differ from Git',()=>{
    const {root,repository,commit}=fixture();
    git(repository,'update-index','--assume-unchanged','desktop/src/main.ts');
    writeFileSync(path.join(root,'src/main.ts'),'export const value=1;\r\n');
    expect(git(repository,'status','--porcelain')).toBe('');
    expect(()=>captureSource(root,commit)).toThrow('SOURCE_INPUT_BYTES_MISMATCH');
  });
  it('retains source failure at final check and never returns a successful build',()=>{
    const {root,commit}=fixture();const evidence=createEvidence(root,undefined,commit);verifySourceBefore(evidence);
    for(const stage of evidence.report.stages){beginStage(evidence,stage.id);endStage(evidence,stage.id,0);}
    writeFileSync(path.join(root,'src/main.ts'),'drift');
    expect(()=>verifySourceAfter(evidence)).toThrow('SOURCE_DIRTY');expect(finishEvidence(evidence)).toBe(1);
    expect(evidence.report).toMatchObject({outcome:'BUILD_FAILED',failureCode:'SOURCE_NOT_VERIFIED',manualAcceptance:'UNTESTED'});
  });
  it('all automatic stages cannot imply source or manual acceptance',()=>{
    const {root,commit}=fixture();const evidence=createEvidence(root,undefined,commit);
    for(const stage of evidence.report.stages){beginStage(evidence,stage.id);endStage(evidence,stage.id,0);}
    expect(finishEvidence(evidence)).toBe(1);
    verifySourceBefore(evidence);verifySourceAfter(evidence);expect(finishEvidence(evidence)).toBe(0);
    expect(evidence.report.manualAcceptance).toBe('UNTESTED');
  });
  it('rejects a changed manifest even with an unchanged commit',()=>{
    const {root,commit}=fixture();const before=captureSource(root,commit);
    expect(()=>assertSameSource(before,{...before,manifestSha256:'wrong'})).toThrow('SOURCE_CHANGED_DURING_BUILD');
  });
  it.skipIf(process.platform==='win32')('rejects linked input even when assume-unchanged hides it',()=>{
    const {root,repository,commit}=fixture();git(repository,'update-index','--assume-unchanged','desktop/src/main.ts');
    rmSync(path.join(root,'src/main.ts'));symlinkSync(path.join(root,'package-lock.json'),path.join(root,'src/main.ts'));
    expect(()=>captureSource(root,commit)).toThrow('SOURCE_INPUT_MISSING_OR_LINKED');
  });
});
describe('safe test summary',()=>{
  const root=path.resolve('test-desktop');
  const result={numTotalTests:3,numPassedTests:1,numFailedTests:0,numPendingTests:1,numTodoTests:1,testResults:[{name:path.join(root,'tests/conditional.test.ts'),assertionResults:[{status:'passed'},{status:'pending',fullName:'private-token'},{status:'todo'}]}]};
  it('preserves skipped and todo counts without raw logs/absolute paths/test inputs',()=>{
    const summary=summarizeTests(result,root);expect(summary).toMatchObject({total:3,passed:1,failed:0,skipped:1,todo:1,files:1});
    expect(summary.skippedCases).toHaveLength(2);expect(JSON.stringify(summary)).not.toContain(root);expect(JSON.stringify(summary)).not.toContain('private-token');
  });
  it('rejects a missing or inconsistent report rather than claiming full success',()=>{
    expect(()=>summarizeTests({},root)).toThrow('TEST_SUMMARY_INVALID');
    expect(()=>summarizeTests({...result,numTotalTests:4},root)).toThrow('TEST_SUMMARY_INVALID');
    expect(()=>summarizeTests({...result,testResults:[{name:'/private/file'}]},root)).toThrow('TEST_SUMMARY_INVALID');
  });
});
