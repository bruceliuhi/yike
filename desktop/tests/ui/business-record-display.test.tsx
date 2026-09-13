// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {CandidateRequestHistory} from '../../src/renderer/pages/opportunities/CandidateRequestHistory';
import {PendingCandidateReviews} from '../../src/renderer/pages/opportunities/PendingCandidateReviews';
import type {CandidateRequestOperation} from '../../src/renderer/domain/candidateRequestOperation';
import {ContactMaterialQuotes} from '../../src/renderer/pages/outreach/ContactMaterialQuotes';
import {AdoptedCoachSummary} from '../../src/renderer/pages/outreach/AdoptedCoachSummary';
import {coachSuggestionSchema} from '../../src/renderer/domain/shortCoach';
import {PUBLIC_SAMPLE} from '../../src/renderer/pages/Opportunities';
const context={service:{},session:{authenticated:false}};
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
afterEach(cleanup);
it('distinguishes request recovery actions without exposing request IDs',()=>{
 const operations=[1,2].map(n=>({key:`key-${n}`,requestId:`internal-request-${n}`,action:'ASSESS',state:'UNKNOWN',retryOf:[]})) as CandidateRequestOperation[];
 const reconcile=vi.fn(),retry=vi.fn();
 render(<CandidateRequestHistory operations={operations} busy={false} onReconcile={reconcile} onRetry={retry}/>);
 expect(screen.queryAllByText('查看请求编号')).toHaveLength(0);
 expect(screen.queryAllByText(/internal-request/)).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'核对原请求 · 记录 2'}));
 expect(reconcile).toHaveBeenCalledWith('key-2');
 fireEvent.click(screen.getByRole('button',{name:'确认后重新判断 · 记录 1'}));
 expect(retry).toHaveBeenCalledWith('key-1');
});
it('distinguishes pending review actions without exposing candidate IDs',()=>{
 const records=[1,2].map(n=>({key:`key-${n}`,candidateId:`internal-candidate-${n}`,requestId:`request-${n}`,action:'INCLUDE' as const,reviewHash:'hash'}));
 const reconcile=vi.fn();render(<PendingCandidateReviews records={records} visibleIds={[]} busy={false} onReconcile={reconcile}/>);
 expect(screen.queryAllByText(/internal-candidate/)).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'核对原复核结果 · 记录 2'}));
 expect(reconcile).toHaveBeenCalledWith(records[1]);
});
it('keeps verbatim material quotes without raw material IDs or versions',()=>{
 const ref={sourceProfileVersionId:'profile',materialId:'internal-material',materialVersion:3,extractionId:'extraction',quote:'真实业务资料原文'};
 render(<ContactMaterialQuotes row={PUBLIC_SAMPLE} disabled draft={{opportunityId:PUBLIC_SAMPLE.id,channel:'dm',version:1,content:ref.quote,savedContent:ref.quote,accountId:'',recipient:'',materialReferences:[ref]}} onChange={vi.fn()}/>);
 expect(screen.getByText(ref.quote)).toBeTruthy();
 expect(screen.queryByText(/internal-material/)).toBeNull();
 expect(screen.queryByText(/版本 3/)).toBeNull();
});
it('keeps adopted source quotes without technical offsets or material identifiers',()=>{
 const candidate=coachSuggestionSchema.parse({
  suggestionId:'test-suggestion',
  binding:{accountScope:{id:'test-space',version:1},requestId:'test-request',opportunityId:PUBLIC_SAMPLE.id,
   profileVersionId:'00000000-0000-4000-8000-000000000001',sourceEvidenceVersion:'internal-evidence',sourceUrl:'https://example.com/source',
   sourceObservedAt:'2026-09-13T00:00:00Z',channel:'dm',draftVersion:1,draftHash:'a'.repeat(64),purpose:'requirement'},
  content:'业务资料原文，方便说说采购需求吗？',question:'方便说说采购需求吗？',context:{summary:'依据原文',quoteIds:['quote']},checks:[],
  quotes:[{id:'quote',text:'采购需求原文',sourceEvidenceVersion:'internal-evidence',sourceUrl:'https://example.com/source',start:0,end:6}],
  materialReferences:[{sourceProfileVersionId:'00000000-0000-4000-8000-000000000001',extractionId:'test-extraction',quote:'业务资料原文',materialId:'internal-material',materialVersion:3}],
  createdAt:'2026-09-13T00:00:00Z',expiresAt:'2026-09-14T00:00:00Z',
 });
 render(<AdoptedCoachSummary candidate={candidate}/>);fireEvent.click(screen.getByRole('button',{name:'查看建议依据'}));
 expect(screen.getByText('采购需求原文')).toBeTruthy();expect(screen.getByText('业务资料原文')).toBeTruthy();
 expect(screen.queryAllByText(/internal-evidence|internal-material|位置 0/)).toHaveLength(0);
});
