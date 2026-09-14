import {describe, expect, it} from 'vitest';
import {resolveXhsSourceTarget} from '../src/main/xhsSourceTarget';
import {rawEvidenceBinding, rawEvidenceFixture} from './fixtures/rawCandidateEvidence';

const noteId='a'.repeat(24), authorId='b'.repeat(24), commentId='c'.repeat(24);
function fixture(kind:'POST'|'COMMENT'='POST') {
  const value=rawEvidenceFixture(), candidate=value.candidate, observation=value.observations.items[0];
  candidate.platform=observation.platform='XIAOHONGSHU';
  candidate.kind=kind; candidate.external_source_id=noteId;
  candidate.external_comment_id=kind==='COMMENT'?commentId:null;
  candidate.current_version.parent=observation.content.parent=null;
  candidate.current_version.author_public_id=observation.content.author_public_id=authorId;
  candidate.current_version.public_url=observation.content.public_url=
    `https://www.xiaohongshu.com/explore/${noteId}${kind==='COMMENT'?`?comment_id=${commentId}`:''}`;
  observation.query='有偿求助 AI';
  observation.execution_context.access_mode='PLATFORM_ACCOUNT';
  observation.execution_context.connection_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd';
  observation.execution_context.connection_version=2;
  return value;
}

describe('XHS source view target from current evidence',()=>{
  it('uses only exact current evidence and its collection connection',()=>{
    const raw=fixture();
    expect(resolveXhsSourceTarget(raw,rawEvidenceBinding)).toEqual({
      noteId,sourceKind:'POST',originalAuthorId:authorId,query:'有偿求助 AI',
      deviceId:raw.observations.items[0].execution_context.device_id,
      connection:{platform:'XIAOHONGSHU',access_mode:'PLATFORM_ACCOUNT',
        connection_id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',connection_version:2},
    });
  });
  it('never treats a comment author as the original post author',()=>{
    expect(resolveXhsSourceTarget(fixture('COMMENT'),rawEvidenceBinding).originalAuthorId).toBeNull();
    expect(resolveXhsSourceTarget(fixture('COMMENT'),rawEvidenceBinding).sourceKind).toBe('COMMENT');
  });
  it('can locate a post with unknown author using its original query',()=>{
    const raw=fixture();raw.candidate.current_version.author_public_id=raw.observations.items[0].content.author_public_id=null;
    expect(resolveXhsSourceTarget(raw,rawEvidenceBinding).originalAuthorId).toBeNull();
  });
  it('rejects a stale UI revision',()=>{
    expect(()=>resolveXhsSourceTarget(fixture(),{...rawEvidenceBinding,candidateRevision:1})).toThrow('SOURCE_VIEW_UNAVAILABLE');
  });
  it.each(['https://example.com/explore/'+noteId,
    `https://www.xiaohongshu.com/explore/${'d'.repeat(24)}`,
    `https://www.xiaohongshu.com/explore/${noteId}?xsec_token=PRIVATE&xsec_source=pc_search`])('rejects mismatched or parameter-bearing source without disclosing it',url=>{
    const raw=fixture();raw.candidate.current_version.public_url=raw.observations.items[0].content.public_url=url;
    expect(()=>resolveXhsSourceTarget(raw,rawEvidenceBinding)).toThrow(/^SOURCE_VIEW_UNAVAILABLE$/);
  });
  it('does not borrow another historical query when current observation is absent',()=>{
    const raw=fixture();const first=raw.observations.items[0];
    raw.observations.items=Array.from({length:100},(_,index)=>({...first,
      observation_id:`${String(index+1).padStart(8,'0')}-aaaa-4aaa-8aaa-aaaaaaaaaaaa`}));
    raw.observations.total=101;raw.observations.truncated=true;
    expect(()=>resolveXhsSourceTarget(raw,rawEvidenceBinding)).toThrow('SOURCE_VIEW_UNAVAILABLE');
  });
  it('does not invent a search when neither original author nor query is available',()=>{
    const raw=fixture('COMMENT');raw.observations.items[0].query=null;
    expect(()=>resolveXhsSourceTarget(raw,rawEvidenceBinding)).toThrow('SOURCE_VIEW_UNAVAILABLE');
  });
});
