import {expect,it} from 'vitest';
import {parseRawCandidateEvidence} from '../src/shared/rawCandidateEvidence';
import {rawEvidenceFixture,rawEvidenceBinding} from './fixtures/rawCandidateEvidence';
export const context=()=>({schema_version:'v2ex-author-context-v1',replies_expected:1,replies_read:1,replies_complete:true,supplements_read:false,author_replies:[{id:'42',body:'已结束',published_at:'2026-09-10T01:00:00Z'}]});
export function evidence(){const raw:any=rawEvidenceFixture();raw.candidate.kind='PAGE';raw.candidate.external_comment_id=null;raw.candidate.external_source_id='12';
 for(const c of [raw.candidate.current_version,raw.observations.items[0].content]){c.parent=null;c.source_context=context();}
 raw.observations.items[0].normalizer_version='v2ex-author-page-v1';return raw;}
it('preserves author updates and count coverage through the raw evidence boundary',()=>{
 const raw=evidence();expect(parseRawCandidateEvidence(raw,rawEvidenceBinding)).toEqual(raw);
});
it.each(['mismatch','future','same_version_change','duplicate','fake_complete','supplement_claim','no_author','wrong_kind'])('rejects invalid source context %s',kind=>{
 const raw=evidence(),c=raw.candidate.current_version.source_context;
 if(kind==='mismatch')c.replies_read=0;if(kind==='future')c.author_replies[0].published_at='2027-01-01T00:00:00Z';
 if(kind==='same_version_change')c.author_replies[0].body='内容不同';if(kind==='duplicate')c.author_replies.push({...c.author_replies[0]});
 if(kind==='fake_complete')c.replies_expected=2;if(kind==='supplement_claim')c.supplements_read=true;
 if(kind==='no_author')raw.candidate.current_version.author_public_id=null;
 if(kind==='wrong_kind')raw.candidate.kind='POST';
 expect(()=>parseRawCandidateEvidence(raw,rawEvidenceBinding)).toThrow('INVALID_RAW_CANDIDATE_EVIDENCE');
});
