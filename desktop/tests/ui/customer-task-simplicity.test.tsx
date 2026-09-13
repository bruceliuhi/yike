// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import {useState} from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {ResearchSettingsPanel} from '../../src/renderer/pages/tasks/ResearchSettings';
import {IndustryTaskStrategyEditor} from '../../src/renderer/pages/tasks/IndustryTaskStrategyEditor';
import {StrategyExecutionLimits} from '../../src/renderer/pages/tasks/StrategyExecutionLimits';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';
import type {IndustryStrategyDraft} from '../../src/renderer/domain/industryTaskStrategy';

afterEach(cleanup);
const usageProps = () => ({value:{...defaultResearchSettings(),maxSoubei:50},onChange:vi.fn(),quote:null,busy:false,error:'',onEstimate:vi.fn(),onCancel:vi.fn()});

it('keeps the usage cap and estimate visible but removes execution teaching from the customer panel',()=>{
  render(<ResearchSettingsPanel {...usageProps()}/>);
  expect(screen.getByRole('spinbutton',{name:'本次最多使用搜贝'})).toBeVisible();
  expect(screen.getByRole('button',{name:'估算用量'})).toBeVisible();
  expect(screen.queryByText('补证顺序')).not.toBeInTheDocument();
  expect(screen.queryByText('停止条件')).not.toBeInTheDocument();
  expect(screen.queryByText('尚未启动')).not.toBeInTheDocument();
  expect(screen.queryByText('计量规则')).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('高级设置'));
  expect(screen.getByRole('spinbutton',{name:'模型调用上限'})).toBeVisible();
  expect(screen.queryByText('计量规则')).not.toBeInTheDocument();
});

it('retains visible actionable errors even while advanced settings are closed',()=>{
  render(<ResearchSettingsPanel {...usageProps()} error="当前服务尚未开放研究，请稍后重试"/>);
  expect(screen.getByText('当前服务尚未开放研究，请稍后重试')).toBeVisible();
});

it('collapses industry details without losing edits or silently changing the profile binding',()=>{
  const initial:IndustryStrategyDraft={profileId:'profile-a',configuration:{version:'industry-task-strategy-v1',sourceTypes:['COMMENT'],intentSignals:['需要软件定制'],counterSignals:[]}};
  function Editor(){const [value,setValue]=useState<IndustryStrategyDraft|undefined>(initial);return <>
    <IndustryTaskStrategyEditor value={value} profileId="profile-a" onChange={setValue}/><output data-testid="strategy">{JSON.stringify(value)}</output>
  </>;}
  render(<Editor/>);
  expect(screen.getByLabelText('任务购买信号')).not.toBeVisible();
  fireEvent.click(screen.getByText('高级设置：客户筛选'));
  expect(screen.getByRole('textbox',{name:'任务购买信号'})).toBeVisible();
  fireEvent.change(screen.getByRole('textbox',{name:'任务购买信号'}),{target:{value:'需要AI系统'}});
  fireEvent.click(screen.getByText('高级设置：客户筛选'));
  expect(screen.getByLabelText('任务购买信号')).not.toBeVisible();
  expect(JSON.parse(screen.getByTestId('strategy').textContent!)).toEqual({...initial,configuration:{...initial.configuration,intentSignals:['需要AI系统']}});
});

it('surfaces incomplete industry settings above the closed editor',()=>{
  render(<IndustryTaskStrategyEditor profileId="current" onChange={vi.fn()} value={{profileId:'old',configuration:{version:'industry-task-strategy-v1',sourceTypes:['COMMENT'],intentSignals:[''],counterSignals:[]}}}/>);
  expect(screen.getByText('客户筛选条件需要核对，请展开高级设置修改。')).toBeVisible();
  expect(screen.getByLabelText('任务购买信号')).not.toBeVisible();
});

it('offers an explicit recommended execution setup without exposing technical fields or adopting it automatically',()=>{
  const onChange=vi.fn();
  render(<StrategyExecutionLimits onChange={onChange}/>);
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByLabelText('最多处理记录数',{selector:'input'})).not.toBeVisible();
  expect(screen.queryByText('执行保护上限')).not.toBeInTheDocument();
  expect(screen.getByText('请采用推荐设置，或展开高级设置调整处理范围。')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'使用推荐设置'}));
  expect(onChange).toHaveBeenCalledWith({max_records:100,max_runtime_seconds:900});
});
