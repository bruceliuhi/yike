import {describe, expect, it, vi} from 'vitest';
import {desktopExecution} from '../src/renderer/services/desktopExecution';
import {desktopStartCommand} from '../src/renderer/pages/tasks/useDesktopExecution';
import {newTaskDraft, type PlatformConnection} from '../src/renderer/domain/models';
import {strategyPrepareRequest} from '../src/renderer/domain/researchStrategies';
import type {StrategyReceipt} from '../src/shared/researchStrategies';
import type {YikeDesktopApi} from '../src/shared/contracts';

function fixture() {
  const draft = {...newTaskDraft(), profileId: crypto.randomUUID(), profileVersion: 1, name: '合成执行配置',
    platforms: ['bilibili', 'web'] as const as unknown as ReturnType<typeof newTaskDraft>['platforms'],
    accounts: {bilibili: '123456'}, terms: [{id: crypto.randomUUID(), value: '采购', origin: 'manual' as const, edited: false}],
    executionLimits: {max_records: 20, max_runtime_seconds: 120}};
  const request = strategyPrepareRequest(draft, crypto.randomUUID(), draft.executionLimits);
  const strategyId = crypto.randomUUID();
  const prepared: StrategyReceipt = {schema_version: 'strategy-confirmation-v1', request_id: request.request_id, operation: 'PREPARE',
    strategy_version_id: strategyId, draft_id: draft.id, draft_revision: draft.revision, profile_version_id: draft.profileId,
    profile_sha256: 'a'.repeat(64), configuration_sha256: 'b'.repeat(64), state: 'DRAFT', recorded_at: '2026-09-10T00:00:00Z',
    snapshot: {strategy_version_id: strategyId, profile_version_id: draft.profileId, configuration: request.configuration,
      platforms: request.platforms, max_records: 20, max_runtime_seconds: 120}};
  const connections: PlatformConnection[] = [{platform: 'bilibili', accountId: '123456', status: 'CONNECTED', capabilities: ['search'],
    registration: {connectionId: crypto.randomUUID(), deviceId: crypto.randomUUID(), version: 2,
      connectedAt: '2026-09-10T00:00:00Z', disconnectedAt: null}}];
  const registration = connections[0].registration!;
  connections[0].foregroundBinding = {mode: 'four-platform-foreground-v1', platform: 'BILIBILI',
    accountPublicId: '123456', connectionId: registration.connectionId, connectionVersion: registration.version,
    deviceId: registration.deviceId};
  connections.push({platform: 'web', status: 'CONNECTED', capabilities: ['search'],
    publicBinding: {sourceId: 'v2ex-latest-v1', deviceId: registration.deviceId}});
  return {draft, prepared, connections};
}

describe('desktop execution renderer adapter', () => {
  it('selects the current foreground registration when the same public account exists on another device', () => {
    const {draft,prepared,connections}=fixture();
    draft.platforms=['xhs']; draft.accounts={...draft.accounts,xhs:'account01'} as typeof draft.accounts;
    const current=strategyPrepareRequest(draft,prepared.request_id,draft.executionLimits);
    prepared.snapshot.configuration=current.configuration; prepared.snapshot.platforms=current.platforms;
    const first:PlatformConnection={...connections[0],platform:'xhs',accountId:'account01',capabilities:['search']};
    first.foregroundBinding={mode:'xhs-foreground-v1',platform:'XIAOHONGSHU',accountPublicId:'account01',
      connectionId:first.registration!.connectionId,connectionVersion:2,deviceId:first.registration!.deviceId};
    const other:PlatformConnection={...first,foregroundBinding:undefined,
      registration:{...first.registration!,connectionId:crypto.randomUUID(),deviceId:crypto.randomUUID()}};
    const command=desktopStartCommand(draft,prepared,[other,first],crypto.randomUUID());
    expect(command.targets[0].connection_id).toBe(first.registration!.connectionId);
  });
  it('keeps older bridges unavailable with no generic HTTP fallback', () => {
    expect(desktopExecution(undefined)).toBeUndefined();
    expect(desktopExecution({} as YikeDesktopApi)).toBeUndefined();
  });
  it('uses only the narrow execution bridge and keeps a stable service identity', async () => {
    const call = vi.fn().mockResolvedValue({state: 'LIST', requests: []});
    const bridge = {executionCommand: call} as unknown as YikeDesktopApi;
    const service = desktopExecution(bridge);
    expect(service).toBeDefined();
    expect(desktopExecution(bridge)).toBe(service);
    expect(await service!.execute({action: 'LIST'})).toEqual({state: 'LIST', requests: []});
    expect(call).toHaveBeenCalledWith({action: 'LIST'});
  });
  it('rejects malformed bridge results without raw error leakage', async () => {
    const service = desktopExecution({executionCommand: vi.fn().mockResolvedValue({state: 'RECORDED', receipt: {secret: 'private'}})} as unknown as YikeDesktopApi);
    await expect(service!.execute({action: 'LIST'})).rejects.toThrow('执行响应未核实');
  });
  it('uses confirmed snapshot identifiers, preserves target order, and never injects device identity', () => {
    const {draft, prepared, connections} = fixture();
    const requestId = crypto.randomUUID();
    const command = desktopStartCommand(draft, prepared, connections, requestId);
    expect(command).toEqual({action: 'START', humanConfirmed: true, requestId, profileVersionId: draft.profileId,
      strategyVersionId: prepared.strategy_version_id, configurationSha256: prepared.configuration_sha256,
      targets: [{platform: 'BILIBILI', access_mode: 'PLATFORM_ACCOUNT', connection_id: connections[0].registration!.connectionId,
        connection_version: 2}, {platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null, connection_version: null}]});
  });
  it('does not silently use anonymous PUBLIC_WEB when an account is selected', () => {
    const {draft, prepared, connections} = fixture();
    draft.accounts = {...draft.accounts, web: 'web-account'} as typeof draft.accounts;
    expect(() => desktopStartCommand(draft, prepared, connections, crypto.randomUUID())).toThrow();
  });
  it.each(['missing', 'ambiguous', 'version', 'device', 'expired', 'mismatch', 'monitor', 'research'])('refuses unsafe execution binding %s', kind => {
    const {draft, prepared, connections} = fixture();
    if (kind === 'missing') connections.length = 0;
    if (kind === 'ambiguous') {
      const connectionId = crypto.randomUUID();
      connections.push({...connections[0], registration: {...connections[0].registration!, connectionId},
        foregroundBinding: {...connections[0].foregroundBinding!, connectionId}});
    }
    if (kind === 'version') connections[0].registration!.version = 0;
    if (kind === 'device') connections[0].registration!.deviceId = 'not-a-device';
    if (kind === 'expired') connections[0].status = 'EXPIRED';
    if (kind === 'mismatch') prepared.snapshot.configuration.name = 'different';
    if (kind === 'monitor') draft.mode = 'monitor';
    if (kind === 'research') Object.assign(draft, {research: {version: 1}});
    expect(() => desktopStartCommand(draft, prepared, connections, crypto.randomUUID())).toThrow();
  });
});
