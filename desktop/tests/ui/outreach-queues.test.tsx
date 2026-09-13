// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { OutreachPage } from '../../src/renderer/pages/Outreach';
import { OutreachQueue } from '../../src/renderer/pages/OutreachQueue';
import '@testing-library/jest-dom/vitest';
import { PUBLIC_SAMPLE } from '../../src/renderer/pages/Opportunities';
import { parseRoute } from '../../src/renderer/domain/routes';
import type { OutreachQueue as Queue, OutreachRecord } from '../../src/renderer/domain/outreach';
import type { AppContextValue } from '../../src/renderer/app/context';
import type { YikeService } from '../../src/renderer/services/contracts';
let context: AppContextValue;
vi.mock('../../src/renderer/app/context', () => ({ useApp: () => context }));
const record = (queue: Queue, extra: Partial<OutreachRecord> = {}): OutreachRecord => ({
  id:'test-record-1', opportunityId:'test-opportunity', channel:'dm', version:2, queue,
  title:'TEST 隔离触达记录', recipientLabel:'TEST 对象', content:'TEST 沟通内容',
  updatedAt:'2026-09-09T09:00:00Z', sample:false, ...extra,
});
beforeEach(() => {
  sessionStorage.clear();
  context = { service:{opportunities:vi.fn().mockResolvedValue([]), opportunity:vi.fn(),
    connections:vi.fn().mockResolvedValue([]), generateContact:vi.fn(), saveContact:vi.fn(),
    outreach:{ queue:vi.fn(), send:vi.fn(), reconcile:vi.fn() },
  } as unknown as YikeService, session:{authenticated:true,userId:crypto.randomUUID()},
    route:parseRoute('#/outreach'), navigate:vi.fn(), notify:vi.fn(), refreshSession:vi.fn() };
});
afterEach(cleanup);
describe('outreach queue contract', () => {
  it('keeps business facts and unresolved result without technical records', async () => {
    vi.mocked(context.service.outreach!.queue).mockResolvedValue({queue:'issues',items:[record('issues',{message:'发送结果未知，请先核对'})],total:1});
    render(<OutreachQueue queue="issues"/>);
    fireEvent.click(await screen.findByRole('button',{name:/TEST 隔离触达记录/}));
    expect(screen.queryByText('查看记录详情')).toBeNull();
    expect(screen.queryByText('test-record-1')).toBeNull();
    expect(screen.getByText('TEST 对象')).toBeVisible();
    expect(screen.getByText('私信')).toBeVisible();
    expect(screen.getByText('TEST 沟通内容')).toBeVisible();
    expect(screen.getByText('发送结果未知，请先核对')).toBeVisible();
    expect(screen.queryByText('草稿版本')).toBeNull();
    expect(context.service.outreach!.send).not.toHaveBeenCalled();
  });
  it.each(['comment','dm'] as const)('opens the actual parent draft workspace from a queue with the selected %s purpose',async channel=>{
    vi.mocked(context.service.outreach!.queue).mockResolvedValue({queue:'confirm',items:[record('confirm',{channel})],total:1});
    vi.mocked(context.service.opportunity).mockResolvedValue({...PUBLIC_SAMPLE,id:'test-opportunity',sample:false,comment:'TEST 评论联系准备',dm:'TEST 私信联系准备'});
    context.navigate=vi.fn((path:string)=>{context.route=parseRoute('#'+path);});
    render(<OutreachPage/>);
    fireEvent.click(screen.getByRole('tab',{name:'待确认'}));
    fireEvent.click(await screen.findByRole('button',{name:/TEST 隔离触达记录/}));
    fireEvent.click(screen.getByRole('button',{name:'查看联系准备'}));
    await screen.findByDisplayValue(channel==='dm'?'TEST 私信联系准备':'TEST 评论联系准备');
    expect(screen.getByRole('tab',{name:'草稿箱'}).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab',{name:channel==='dm'?'私信草稿':'评论草稿'}).getAttribute('aria-selected')).toBe('true');
    expect(screen.queryByRole('region',{name:'待确认队列'})).toBeNull();
    expect(context.service.opportunity).toHaveBeenCalledWith('test-opportunity');
  });
  it.each(['confirm','reply','issues'] as const)('loads %s records and navigates using opportunity identity + channel', async queue => {
    vi.mocked(context.service.outreach!.queue).mockResolvedValue({queue,items:[record(queue)],total:1});
    render(<OutreachQueue queue={queue}/>);
    fireEvent.click(await screen.findByRole('button',{name:/TEST 隔离触达记录/}));
    expect(screen.queryByText('test-record-1')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'查看联系准备'}));
    expect(context.navigate).toHaveBeenCalledWith('/outreach?opportunity=test-opportunity&channel=dm');
  });
  it('handles loading, failure and refresh without retaining old content',async()=>{
    let resolve!: (v:unknown)=>void;
    vi.mocked(context.service.outreach!.queue).mockImplementationOnce(()=>new Promise(r=>{resolve=r as typeof resolve}));
    render(<OutreachQueue queue="reply"/>);
    expect(screen.queryByText('暂无待回复记录')).toBeNull();
    await waitFor(()=>expect(context.service.outreach!.queue).toHaveBeenCalledOnce());
    await act(async()=>resolve({queue:'reply',items:[record('reply')],total:1}));
    await screen.findByText('TEST 隔离触达记录');
    vi.mocked(context.service.outreach!.queue).mockRejectedValueOnce(new Error('TEST 查询失败'));
    fireEvent.click(screen.getByRole('button',{name:'刷新记录'}));
    await screen.findByText('TEST 查询失败');
    expect(screen.queryByText('TEST 隔离触达记录')).toBeNull();
    vi.mocked(context.service.outreach!.queue).mockResolvedValue({queue:'reply',items:[],total:0});
    fireEvent.click(screen.getByRole('button',{name:'刷新记录'}));
    await screen.findByText('暂无待回复记录');
  });
  it('default unavailable is distinct from an empty queue', async()=>{
    context.service.outreach=undefined;
    render(<OutreachQueue queue="confirm"/>);
    await screen.findByText('触达队列与发送结果核对服务尚未接通。');
    expect(screen.queryByText('暂无待确认记录')).toBeNull();
  });
  it.each(['wrong queue','duplicate ids','partial snapshot','malformed date'])('rejects %s rather than showing actionable records',async kind=>{
    const rows=[record('confirm')]; const result={queue:'confirm',items:rows,total:1};
    if(kind==='wrong queue') rows[0].queue='reply';
    if(kind==='duplicate ids'){rows.push(record('confirm'));result.total=2;}
    if(kind==='partial snapshot')result.total=2;
    if(kind==='malformed date')rows[0].updatedAt='not-a-date';
    vi.mocked(context.service.outreach!.queue).mockResolvedValue(result as never);
    render(<OutreachQueue queue="confirm"/>);
    await screen.findByRole('alert');
    expect(screen.queryByText('TEST 隔离触达记录')).toBeNull();
  });
  it('samples are read-only and cannot navigate to the send workspace',async()=>{
    vi.mocked(context.service.outreach!.queue).mockResolvedValue({queue:'issues',items:[record('issues',{sample:true})],total:1});
    render(<OutreachQueue queue="issues"/>);
    fireEvent.click(await screen.findByRole('button',{name:/TEST 隔离触达记录/}));
    expect(screen.queryByRole('button',{name:'查看联系准备'})).toBeNull();
    expect(context.service.outreach!.send).not.toHaveBeenCalled();
  });
  it('does not query as guest or retain records across account changes',async()=>{
    vi.mocked(context.service.outreach!.queue).mockResolvedValue({queue:'reply',items:[record('reply')],total:1});
    const view=render(<OutreachQueue queue="reply"/>);
    await screen.findByText('TEST 隔离触达记录');
    context={...context,session:{authenticated:false}};
    view.rerender(<OutreachQueue queue="reply"/>);
    expect(screen.queryByText('TEST 隔离触达记录')).toBeNull();
    expect(context.service.outreach!.queue).toHaveBeenCalledTimes(1);
  });
});
describe('first draft and manual edits',()=>{
  function setup(){
    context.route=parseRoute('#/outreach?opportunity=test-opportunity&channel=dm');
    vi.mocked(context.service.opportunity).mockResolvedValue({...PUBLIC_SAMPLE,id:'test-opportunity',sample:false,comment:'',dm:''});
  }
  it('offers initial generation, retries failure and previews without overwriting manual text',async()=>{
    setup();
    vi.mocked(context.service.generateContact!).mockRejectedValueOnce(new Error('TEST 生成失败')).mockResolvedValueOnce('TEST 新建议');
    render(<OutreachPage/>);
    fireEvent.click(await screen.findByRole('button',{name:'生成联系草稿'}));
    await screen.findByText('TEST 生成失败');
    fireEvent.change(screen.getByRole('textbox',{name:'沟通内容'}),{target:{value:'TEST 人工编辑'}});
    fireEvent.click(screen.getByRole('button',{name:'重试生成'}));
    await screen.findByRole('dialog',{name:'新草稿预览'});
    expect((screen.getByRole('textbox',{name:'沟通内容'}) as HTMLTextAreaElement).value).toBe('TEST 人工编辑');
    expect(context.service.generateContact).toHaveBeenLastCalledWith('test-opportunity','dm');
    fireEvent.click(screen.getByRole('button',{name:'保留当前内容'}));
    expect((screen.getByRole('textbox',{name:'沟通内容'}) as HTMLTextAreaElement).value).toBe('TEST 人工编辑');
  });
  it('empty generation is failure and cannot replace text',async()=>{
    setup(); vi.mocked(context.service.generateContact!).mockResolvedValue('  ');
    render(<OutreachPage/>);
    fireEvent.click(await screen.findByRole('button',{name:'生成联系草稿'}));
    await screen.findByText('未生成可用草稿，当前内容已保留，请重试生成。');
    expect(screen.queryByRole('dialog',{name:'新草稿预览'})).toBeNull();
  });
  it('rejects a detail response for another opportunity',async()=>{
    setup();vi.mocked(context.service.opportunity).mockResolvedValue({...PUBLIC_SAMPLE,id:'wrong',sample:false});
    render(<OutreachPage/>);
    await screen.findByText('商机返回记录与当前选择不匹配，请刷新重试。');
    expect(screen.queryByRole('textbox',{name:'沟通内容'})).toBeNull();
  });
  it('keeps edits made while generation is pending until explicit replacement',async()=>{
    setup(); let resolve!: (v:string)=>void;
    vi.mocked(context.service.generateContact!).mockImplementation(()=>new Promise(r=>{resolve=r}));
    render(<OutreachPage/>);
    fireEvent.click(await screen.findByRole('button',{name:'生成联系草稿'}));
    fireEvent.change(screen.getByRole('textbox',{name:'沟通内容'}),{target:{value:'TEST 生成期间人工编辑'}});
    await waitFor(()=>expect(context.service.generateContact).toHaveBeenCalledOnce());
    await act(async()=>resolve('TEST 建议'));
    await screen.findByText('生成期间你修改了草稿；当前编辑仍完整保留。');
    expect((screen.getByRole('textbox',{name:'沟通内容'}) as HTMLTextAreaElement).value).toBe('TEST 生成期间人工编辑');
    fireEvent.click(screen.getByRole('button',{name:'替换当前草稿'}));
    await waitFor(()=>expect((screen.getByRole('textbox',{name:'沟通内容'}) as HTMLTextAreaElement).value).toBe('TEST 建议'));
  });
});
