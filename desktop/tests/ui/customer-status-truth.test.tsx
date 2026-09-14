// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {CandidateRequestHistory} from '../../src/renderer/pages/opportunities/CandidateRequestHistory';
import {DisconnectPanel} from '../../src/renderer/pages/connections/DisconnectPanel';
import type {CandidateRequestOperation} from '../../src/renderer/domain/candidateRequestOperation';

afterEach(cleanup);
function operation(state:CandidateRequestOperation['state']):CandidateRequestOperation {
  return {v:1,key:state,scopeId:null,scopeVersion:null,candidateId:'test',requestId:'test',
    action:'ASSESS',binding:[1,'test','test',1],requestHash:'0'.repeat(64),assessmentId:null,
    verification:[],retryOf:[],invocationId:null,state};
}

it('keeps definite failure visible outside folded request history',()=>{
  const retry=vi.fn();
  render(<CandidateRequestHistory operations={[operation('FAILED')]} busy={false} onReconcile={vi.fn()} onRetry={retry}/>);
  const status=screen.getByRole('status');
  expect(status.textContent).toContain('判断失败');
  expect(status.closest('details')).toBeNull();
  const summary=screen.getByText('查看处理记录（1）');
  expect(summary.closest('details')!.open).toBe(false);
  fireEvent.click(summary);
  fireEvent.click(screen.getByRole('button',{name:'确认后重新判断'}));
  expect(retry).toHaveBeenCalledWith('FAILED');
});

it('keeps unknown results distinct from failed results',()=>{
  render(<CandidateRequestHistory operations={[operation('UNKNOWN')]} busy={false} onReconcile={vi.fn()} onRetry={vi.fn()}/>);
  expect(screen.getByRole('status').textContent).toContain('待确认');
  expect(screen.getByRole('status').textContent).not.toContain('失败');
});

it('does not describe an idle acknowledged disconnect as an active check',()=>{
  const check=vi.fn();
  const pending={key:'test',platform:'xhs' as const,accountId:'test',requestId:'test',acknowledged:true};
  render(<DisconnectPanel action={{identity:{},target:pending,phase:'idle',message:'',records:[pending],
    pending,busy:false,open:vi.fn(),openRecord:vi.fn(),close:vi.fn(),start:vi.fn(),check,assertConnectable:vi.fn()}}/>);
  expect(screen.queryByText('正在确认账号是否已断开。')).toBeNull();
  expect(screen.getByText('断开结果待确认，请检查连接状态。')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'核对连接状态'}));
  expect(check).toHaveBeenCalledOnce();
});
