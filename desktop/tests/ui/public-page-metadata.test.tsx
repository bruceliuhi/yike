// @vitest-environment jsdom
import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { CandidateOriginalEvidence } from '../../src/renderer/pages/opportunities/CandidateOriginalEvidence';
import { FixedSourceEvidence } from '../../src/renderer/pages/opportunities/FixedSourceEvidence';
import { parseRawCandidateEvidence } from '../../src/shared/rawCandidateEvidence';
import { parseOpportunitySourceEvidence } from '../../src/renderer/domain/opportunitySourceEvidence';
import { rawEvidenceBinding } from '../fixtures/rawCandidateEvidence';
import { pageMetadataFixture, publicPageCandidateFixture, publicPageFixedFixture } from '../fixtures/publicPageMetadata';

afterEach(cleanup);

it.each(['candidate', 'fixed'])('renders declared metadata separately from buyer identity in the %s panel', panel => {
  const metadata = pageMetadataFixture();
  if (panel === 'candidate') render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(publicPageCandidateFixture(metadata), rawEvidenceBinding)} />);
  else {
    const evidence = parseOpportunitySourceEvidence(publicPageFixedFixture(metadata), { opportunityId: 'TEST-o', profileVersionId: 'TEST-p' });
    if (evidence.status !== 'CAPTURED') throw new Error('TEST fixture');
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);
  }
  const region = screen.getByRole('region', { name: panel === 'candidate' ? '当前原文' : '固定原文证据快照' });
  const view = within(region);
  expect(view.getByText('公开作者').nextElementSibling?.textContent).toBe('未知');
  expect(view.getByText('网页标注作者').nextElementSibling?.textContent).toBe('TEST 编辑部');
  const date = view.getByText('网页标注发布日期').nextElementSibling!;
  expect(date.textContent).toBe('2026-09-09（仅日期，时区未知）');
  expect(date.querySelector('time')?.getAttribute('datetime')).toBe('2026-09-09');
  expect(date.textContent).not.toContain('00:00');
  expect(view.getByText(/网页声明，不代表已核验的买方身份或需求日期/)).toBeTruthy();
  const details = view.getByText('网页声明原值').closest('details');
  expect(details?.open).toBe(false);
  fireEvent.click(view.getByText('网页声明原值'));
  expect(details?.open).toBe(true);
  expect(details?.textContent).toContain('article:published_time');
  expect(details?.textContent).toContain(metadata.publication!.raw);
  expect(details?.textContent).toContain('author');
});

it.each([
  ['candidate', 'LOCAL_SECOND'], ['fixed', 'LOCAL_SECOND'],
  ['candidate', 'SECOND'], ['fixed', 'SECOND'],
])('renders %s %s without inferring timezone or dropping seconds', (panel, precision) => {
  const metadata = pageMetadataFixture(precision);
  if (panel === 'candidate') render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(publicPageCandidateFixture(metadata), rawEvidenceBinding)} />);
  else {
    const evidence = parseOpportunitySourceEvidence(publicPageFixedFixture(metadata), { opportunityId: 'TEST-o', profileVersionId: 'TEST-p' });
    if (evidence.status !== 'CAPTURED') throw new Error('TEST fixture');
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);
  }
  const region = screen.getByRole('region', { name: panel === 'candidate' ? '当前原文' : '固定原文证据快照' });
  const time = within(region).getByText('网页标注发布时间').nextElementSibling!;
  expect(time.textContent).toBe(precision === 'SECOND' ? '2026-09-09 01:02:03（UTC）' : '2026-09-09 09:02:03（时区未知）');
  expect(time.querySelector('time')?.getAttribute('datetime')).toBe(metadata.publication!.value);
});
