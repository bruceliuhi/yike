// @vitest-environment jsdom
import {webcrypto} from 'node:crypto';
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {validatedOperation} from '../../src/main/servicePolicy';
import {service} from '../../src/renderer/services/client';
import {useUsageQuote} from '../../src/renderer/pages/tasks/useUsageQuote';
import {newTaskDraft, type TaskDraft} from '../../src/renderer/domain/models';
import {defaultResearchSettings, parseUsageQuote, type UsageQuote} from '../../src/renderer/domain/researchUsage';
import type {AppContextValue} from '../../src/renderer/app/context';
import type {StrategyReceipt} from '../../src/shared/researchStrategies';
import type {YikeDesktopApi} from '../../src/shared/contracts';

let context: AppContextValue;
vi.mock('../../src/renderer/app/context', () => ({useApp: () => context}));
const uuid = '11111111-1111-4111-8111-111111111111';
const strategyBinding = {strategyVersionId: uuid, profileVersionId: uuid, configurationSha256: 'a'.repeat(64)};
const input = {contractVersion: 1 as const, requestId: uuid, userId: 'test-user', accountScopeId: 'test-space',
  accountScopeVersion: 1, draftId: 'test-draft', revision: 1, configurationHash: 'b'.repeat(64), maxSoubei: 50, strategyBinding};
const response = (request: typeof input) => ({...request, quoteId: uuid, ruleVersion: 'TEST-only', ruleSha256: 'c'.repeat(64),
  authorizationToken: 'TEST-token', estimatedSoubei: 10, generatedAt: new Date(Date.now()-1000).toISOString(),
  expiresAt: new Date(Date.now()+60000).toISOString(), basis: 'TEST 资源上限估算，非实际消耗，未预留'});
const host = window as unknown as {yikeDesktop?: YikeDesktopApi};
beforeEach(() => {vi.stubGlobal('crypto', webcrypto);});
afterEach(() => {cleanup(); delete host.yikeDesktop; vi.unstubAllGlobals();});

describe('confirmed strategy quote transport', () => {
  it('routes only the bounded confirmed request and refuses missing server binding', () => {
    expect(validatedOperation({operation: 'researchUsage.quote', payload: input})).toMatchObject({
      path: '/api/ui/research-usage/quote', method: 'POST', body: JSON.stringify(input), logout: false,
    });
    const {strategyBinding: _binding, ...legacy} = input;
    expect(validatedOperation({operation: 'researchUsage.quote', payload: legacy})).toBeNull();
  });
  it.each([' ', '\n', '\u2028', '\u2029'])('rejects identity padding or controls %j before transport', suffix => {
    expect(validatedOperation({operation: 'researchUsage.quote', payload: {...input, userId: input.userId+suffix}})).toBeNull();
  });
  it('ordinary service sends no draft or source text and verifies returned binding', async () => {
    const call = vi.fn().mockResolvedValue({ok: true, status: 200, data: response(input)});
    host.yikeDesktop = {requestApi: call} as unknown as YikeDesktopApi;
    expect(service.researchUsage).toBeDefined();
    expect(service.researchUsage?.requiresConfirmedStrategy).toBe(true);
    const quote = await service.researchUsage!.quote(input, newTaskDraft());
    expect(quote.strategyBinding).toEqual(strategyBinding);
    expect(call).toHaveBeenCalledWith({operation: 'researchUsage.quote', payload: input});
    call.mockResolvedValue({ok: true, status: 200, data: {...response(input), strategyBinding: {...strategyBinding, configurationSha256: 'd'.repeat(64)}}});
    await expect(service.researchUsage!.quote(input, newTaskDraft())).rejects.toThrow();
  });
  it('compares nested bindings structurally and requires a rule digest for real quotes', () => {
    expect(parseUsageQuote(structuredClone(response(input)), input).strategyBinding).toEqual(strategyBinding);
    const {ruleSha256: _rule, ...missingRule} = response(input);
    expect(() => parseUsageQuote(missingRule, input)).toThrow();
  });
});

describe('confirmed quote hook', () => {
  function setup() {
    const draft: TaskDraft = {...newTaskDraft(), id: input.draftId, profileId: uuid,
      executionLimits: {max_records: 10, max_runtime_seconds: 60},
      research: {...defaultResearchSettings(), maxSoubei: 50}};
    context = {service: {researchUsage: {requiresConfirmedStrategy: true, quote: vi.fn(async value => response(value as typeof input))}},
      session: {authenticated: true, userId: input.userId, accountScope: {id: input.accountScopeId, version: 1}}} as unknown as AppContextValue;
    const prepared = {strategy_version_id: uuid, profile_version_id: uuid, configuration_sha256: 'a'.repeat(64),
      draft_id: draft.id, draft_revision: draft.revision, snapshot: {max_records: 10, max_runtime_seconds: 60}} as StrategyReceipt;
    return {draft, strategy: {confirmed: true, prepared, recheck: vi.fn().mockResolvedValue(true)}};
  }
  it('does not query before strategy confirmation', async () => {
    const {draft, strategy} = setup();
    const hook = renderHook(() => useUsageQuote(draft, {...strategy, confirmed: false}));
    await act(() => hook.result.current.estimate());
    expect(context.service.researchUsage!.quote).not.toHaveBeenCalled();
    expect(hook.result.current.error).toContain('确认');
  });
  it('binds the server digest and drops late results when execution limits change', async () => {
    const {draft, strategy} = setup();
    let done!: (value: UsageQuote) => void;
    context.service.researchUsage!.quote = vi.fn(() => new Promise<UsageQuote>(resolve => {done = resolve;}));
    const hook = renderHook(({value}) => useUsageQuote(value, strategy), {initialProps: {value: draft}});
    let pending!: Promise<void>;
    await act(async () => {pending = hook.result.current.estimate();});
    await waitFor(() => expect(context.service.researchUsage!.quote).toHaveBeenCalled());
    const request = vi.mocked(context.service.researchUsage!.quote).mock.calls[0][0];
    expect(request.strategyBinding).toEqual(strategyBinding);
    expect(strategy.recheck).toHaveBeenCalledOnce();
    hook.rerender({value: {...draft, executionLimits: {max_records: 20, max_runtime_seconds: 60}}});
    await act(async () => {done(response(request as typeof input)); await pending;});
    expect(hook.result.current.quote).toBeNull();
    expect(hook.result.current.valid).toBe(false);
  });
});
