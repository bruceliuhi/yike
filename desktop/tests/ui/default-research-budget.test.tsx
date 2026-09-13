// @vitest-environment jsdom
import {cleanup, render, renderHook, screen} from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
import {taskDraftOwner, useTaskDraft} from '../../src/renderer/app/taskDraft';
import {newTaskDraft} from '../../src/renderer/domain/models';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';
import {ResearchSettingsPanel} from '../../src/renderer/pages/tasks/ResearchSettings';

beforeEach(()=>{clearLocalDrafts(); sessionStorage.clear(); localStorage.clear();});
afterEach(cleanup);

it.each(['once','monitor'] as const)('defaults a fresh %s task to 100000 soubei without raising execution limits',mode=>{
  const {result}=renderHook(()=>useTaskDraft('TEST-user',mode));
  expect(result.current[0].research?.maxSoubei).toBe(100_000);
  expect(result.current[0].research?.limits).toEqual({sources:100,minutes:15,modelCalls:50});
  expect(result.current[0].research?.stopAtAnyLimit).toBe(true);
});

it('shows the default budget without requiring a first edit or triggering an estimate',()=>{
  const onEstimate=vi.fn();
  render(<ResearchSettingsPanel value={defaultResearchSettings()} onChange={vi.fn()}
    quote={null} busy={false} error="" onEstimate={onEstimate} onCancel={vi.fn()}/>);
  expect(screen.getByRole('spinbutton',{name:'本次最多使用搜贝'})).toHaveValue(100_000);
  expect(onEstimate).not.toHaveBeenCalled();
});

it('preserves the explicit budget in an existing draft',()=>{
  const draft={...newTaskDraft(),research:{...defaultResearchSettings(),maxSoubei:50}};
  const owner=crypto.randomUUID();
  sessionStorage.setItem('yike.ui.draft.v1.task.'+taskDraftOwner(owner),JSON.stringify(draft));
  const {result}=renderHook(()=>useTaskDraft(owner));
  expect(result.current[0].research?.maxSoubei).toBe(50);
});
