// @vitest-environment jsdom
import React from 'react';
import {expect,it} from 'vitest';
import {render,screen,within,cleanup} from '@testing-library/react';
import {CandidateOriginalEvidence} from '../../src/renderer/pages/opportunities/CandidateOriginalEvidence';
import {parseRawCandidateEvidence} from '../../src/shared/rawCandidateEvidence';
import {rawEvidenceFixture,rawEvidenceBinding} from '../fixtures/rawCandidateEvidence';
it('shows actual author update separately and does not imply supplements were read',()=>{
 const raw:any=rawEvidenceFixture();raw.candidate.kind='PAGE';raw.candidate.external_comment_id=null;raw.candidate.external_source_id='12';
 for(const c of [raw.candidate.current_version,raw.observations.items[0].content]){c.parent=null;c.source_context={schema_version:'v2ex-author-context-v1',replies_expected:2,replies_read:1,replies_complete:false,supplements_read:false,author_replies:[{id:'42',body:'已结束',published_at:'2026-09-10T01:00:00Z'}]};}
 raw.observations.items[0].normalizer_version='v2ex-author-page-v1';
 render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw,rawEvidenceBinding)}/>);
 const current=within(screen.getByRole('region',{name:'当前原文'}));
 expect(current.getByText('已结束')).toBeTruthy();expect(current.getByText(/回复读取不全/)).toBeTruthy();expect(current.getByText(/附言未读/)).toBeTruthy();cleanup();
});
