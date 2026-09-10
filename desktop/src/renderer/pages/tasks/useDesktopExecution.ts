import {desktopExecutionCommandSchema, desktopExecutionResultSchema, type DesktopExecutionCommand} from '../../../shared/desktopExecution';
import {strategyReceiptSchema, type StrategyReceipt} from '../../../shared/researchStrategies';
import {deviceUuidSchema} from '../../../shared/deviceRegistration';
import type {PlatformConnection, TaskDraft} from '../../domain/models';
import {strategyPrepareRequest} from '../../domain/researchStrategies';
import {validStrategyExecutionLimits} from '../../domain/strategyExecutionLimits';
import {ServiceError} from '../../services/contracts';
import type {ExecutionOperation} from '../../../shared/executionOperation';
import {parseExecutionReceipt, type ExecutionReceipt} from '../../../shared/executionReceipt';
import {useEffect, useRef, useState} from 'react';
import {useApp} from '../../app/context';
import {boundedRequest} from '../../app/boundedRequest';
import {useTaskScope} from './useTaskScope';
import {hasForegroundBinding} from '../../domain/task';
import {foregroundCollectionCommandSchema, foregroundCollectionResultSchema,
  type ForegroundCollectionResult} from '../../../shared/foregroundCollection';

export type DesktopStartCommand = Extract<DesktopExecutionCommand, {action: 'START'}>;
export interface DesktopExecutionEntry {
  requestId: string;
  operation: ExecutionOperation['operation'];
  request?: ExecutionOperation;
  command?: Exclude<DesktopExecutionCommand, {action: 'LIST' | 'RECOVER'}>;
  receipt?: ExecutionReceipt;
  state?: string;
  collection?: ForegroundCollectionResult;
}
function startBinding(entry: DesktopExecutionEntry) {
  if (entry.request?.operation === 'START') return {profileVersionId: entry.request.profile_version_id,
    strategyVersionId: entry.request.strategy_version_id, configurationSha256: entry.request.configuration_sha256,
    targets: entry.request.targets};
  if (entry.command?.action === 'START') return {profileVersionId: entry.command.profileVersionId,
    strategyVersionId: entry.command.strategyVersionId, configurationSha256: entry.command.configurationSha256,
    targets: entry.command.targets};
  return null;
}
export function useDesktopExecution(prepared: StrategyReceipt | null) {
  const {service, session} = useApp();
  const api = service.execution;
  const collectionApi = service.foregroundCollection;
  const scope = useTaskScope();
  type State = {identity: object; entries: DesktopExecutionEntry[]; loaded: boolean; busy: boolean; error: string};
  const empty = (): State => ({identity: scope.identity, entries: [], loaded: false, busy: false, error: ''});
  const [state, setState] = useState<State>(empty);
  const latest = useRef(state);
  if (latest.current.identity !== scope.identity) latest.current = empty();
  const active = useRef(new Set<object>());
  const shown = state.identity === scope.identity ? state : empty();
  function show(patch: Partial<State>) {
    if (!scope.current()) return;
    latest.current = {...latest.current, ...patch};
    setState(latest.current);
  }
  function save(entry: DesktopExecutionEntry) {
    show({entries: [...latest.current.entries.filter(value => value.requestId !== entry.requestId), entry]});
  }
  async function run(operation: () => Promise<void>) {
    if (!api || !session.authenticated || !scope.current() || active.current.has(scope.identity)) return;
    active.current.add(scope.identity);
    show({busy: true, error: ''});
    try { await operation(); }
    catch { show({error: '执行响应未核实，原请求已保留。请核对原请求，不要重复启动或取消。'}); }
    finally { active.current.delete(scope.identity); show({busy: false}); }
  }
  const call = async (command: DesktopExecutionCommand) => {
    if (!scope.current()) throw new Error();
    return desktopExecutionResultSchema.parse(await boundedRequest(() => {
      if (!scope.current()) throw new Error();
      return api!.execute(command);
    }, {timeoutMessage: '执行等待超时，原请求已保留，请核对原请求。'}));
  };
  const refresh = () => run(async () => {
    show({loaded: false});
    const result = await call({action: 'LIST'});
    if (!scope.current()) return;
    if (result.state !== 'LIST') throw new Error();
    const entries = new Map(latest.current.entries.map(entry => [entry.requestId, entry]));
    for (const request of result.requests) entries.set(request.request_id, {...entries.get(request.request_id),
      requestId: request.request_id, operation: request.operation, request});
    show({loaded: true, entries: [...entries.values()]});
  });
  useEffect(() => { if (api && session.authenticated) void refresh(); }, [scope.identity, api]);
  async function dispatch(entry: DesktopExecutionEntry, command: DesktopExecutionCommand) {
    const result = await call(command);
    if (!scope.current()) return;
    if (result.state === 'LIST') throw new Error();
    if (result.state === 'UNKNOWN' && result.requestId !== entry.requestId) throw new Error();
    if (result.state === 'RECORDED') {
      if (result.receipt.request_id !== entry.requestId || result.receipt.operation !== entry.operation) throw new Error();
      const receipt = entry.request ? parseExecutionReceipt(result.receipt, entry.request) : result.receipt;
      const binding = startBinding(entry);
      if (binding && receipt.operation === 'START' &&
          (receipt.platform_runs.length !== binding.targets?.length || receipt.platform_runs.some((row, index) => row.platform !== binding.targets![index].platform))) throw new Error();
      if (entry.command?.action === 'CANCEL' && receipt.task_id !== entry.command.taskId) throw new Error();
      save({...entry, state: 'RECORDED', receipt});
    } else save({...entry, state: result.state});
  }
  const start = (input: DesktopStartCommand) => run(async () => {
    const command = desktopExecutionCommandSchema.parse(input) as DesktopStartCommand;
    if (!latest.current.loaded || command.action !== 'START') throw new Error();
    if (latest.current.entries.some(entry => {
      const binding = startBinding(entry);
      return binding?.strategyVersionId === command.strategyVersionId && binding.configurationSha256 === command.configurationSha256 &&
        binding.profileVersionId === command.profileVersionId;
    })) throw new Error();
    const entry: DesktopExecutionEntry = {requestId: command.requestId, operation: 'START', command, state: 'UNKNOWN'};
    save(entry); // Retain the UUID before IPC; the main process persists its complete original operation.
    await dispatch(entry, command);
  });
  const recover = (supplied: DesktopExecutionEntry, retry = false, validate?: () => Promise<DesktopStartCommand>) => run(async () => {
    const entry = latest.current.entries.find(value => value.requestId === supplied.requestId);
    if (!entry || !latest.current.loaded) throw new Error();
    if (retry && entry.operation === 'START') {
      if (!validate) throw new Error();
      const command = desktopExecutionCommandSchema.parse(await validate()) as DesktopStartCommand;
      if (!scope.current() || command.action !== 'START' || command.requestId !== entry.requestId ||
          JSON.stringify(startBinding({requestId: command.requestId, operation: 'START', command})) !== JSON.stringify(startBinding(entry))) throw new Error();
    } else if (retry && entry.operation !== 'CANCEL') throw new Error();
    await dispatch(entry, {action: 'RECOVER', requestId: entry.requestId, ...(retry ? {retry: true, humanConfirmed: true} : {})});
  });
  const submitCancel = async (taskId: string, humanConfirmed: boolean) => {
    if (!latest.current.loaded || humanConfirmed !== true) throw new Error();
    if (latest.current.entries.some(value => value.operation === 'CANCEL' &&
        (value.request?.task_id === taskId || value.command?.action === 'CANCEL' && value.command.taskId === taskId))) throw new Error();
    const command = desktopExecutionCommandSchema.parse({action: 'CANCEL', requestId: crypto.randomUUID(), taskId, humanConfirmed: true}) as Extract<DesktopExecutionCommand, {action: 'CANCEL'}>;
    const pending: DesktopExecutionEntry = {requestId: command.requestId, operation: 'CANCEL', command, state: 'UNKNOWN'};
    save(pending);
    await dispatch(pending, command);
  };
  const cancelTask = (taskId: string, humanConfirmed: boolean) => run(() => submitCancel(taskId, humanConfirmed));
  const cancel = (supplied: DesktopExecutionEntry, humanConfirmed: boolean) => run(async () => {
    const entry = latest.current.entries.find(value => value.requestId === supplied.requestId);
    if (!entry?.receipt || entry.receipt.operation !== 'START') throw new Error();
    await submitCancel(entry.receipt.task_id, humanConfirmed);
  });
  const collection = (supplied: DesktopExecutionEntry, recover: boolean, humanConfirmed = false) => run(async () => {
    const entry = latest.current.entries.find(value => value.requestId === supplied.requestId);
    if (!collectionApi || !latest.current.loaded || entry?.receipt?.operation !== 'START') throw new Error();
    if (recover && (humanConfirmed !== true || entry.collection?.state !== 'STATUS' || !entry.collection.recoverable)) throw new Error();
    const taskId = entry.receipt.task_id;
    const command = foregroundCollectionCommandSchema.parse(recover
      ? {action:'RECOVER', taskId, humanConfirmed:true, retry:true} : {action:'STATUS', taskId});
    save({...entry, collection:undefined});
    const result = foregroundCollectionResultSchema.parse(await boundedRequest(() => {
      if (!scope.current()) throw new Error();
      return collectionApi.execute(command);
    }, {timeoutMessage:'采集状态等待超时，原批次已保留；请重新查询。'}));
    if (!scope.current()) return;
    if (result.state === 'AVAILABLE' || result.state === 'STATUS' && result.taskId !== taskId) throw new Error();
    save({...entry, collection:result});
  });
  const blocksStart = !shown.loaded || shown.entries.some(entry => {
    const binding = startBinding(entry);
    return prepared && binding?.strategyVersionId === prepared.strategy_version_id &&
      binding.configurationSha256 === prepared.configuration_sha256 && binding.profileVersionId === prepared.profile_version_id;
  });
  return {...shown, blocksStart, refresh, start, recover, cancel, cancelTask,
    collectionAvailable:!!collectionApi,
    collectionStatus:(entry:DesktopExecutionEntry) => collection(entry, false),
    recoverCollection:(entry:DesktopExecutionEntry, confirmed:boolean) => collection(entry, true, confirmed)};
}
export function desktopStartCommand(draft: TaskDraft, prepared: StrategyReceipt, connections: PlatformConnection[], requestId: string): DesktopStartCommand {
  try {
    const limits = validStrategyExecutionLimits(draft.executionLimits);
    if (draft.mode !== 'once' || draft.research || !limits) throw new Error();
    const receipt = strategyReceiptSchema.parse(prepared);
    const current = strategyPrepareRequest(draft, receipt.request_id, limits);
    if (receipt.draft_id !== draft.id || receipt.draft_revision !== draft.revision || receipt.profile_version_id !== draft.profileId ||
        JSON.stringify(receipt.snapshot.configuration) !== JSON.stringify(current.configuration) ||
        JSON.stringify(receipt.snapshot.platforms) !== JSON.stringify(current.platforms) ||
        receipt.snapshot.max_records !== limits.max_records || receipt.snapshot.max_runtime_seconds !== limits.max_runtime_seconds) throw new Error();
    const platformCodes = {xhs: 'XIAOHONGSHU', douyin: 'DOUYIN', bilibili: 'BILIBILI', zhihu: 'ZHIHU', web: 'PUBLIC_WEB'} as const;
    const devices = new Set<string>();
    const targets = draft.platforms.map(platform => {
      const accountId = draft.accounts[platform];
      if (platform === 'web' && !accountId) return {platform: 'PUBLIC_WEB' as const, access_mode: 'PUBLIC_ANONYMOUS' as const,
        connection_id: null, connection_version: null};
      const foreground = connections.some(row => row.platform === platform && hasForegroundBinding(row));
      const matches = connections.filter(row => row.platform === platform && row.accountId === accountId &&
        row.status === 'CONNECTED' && row.registration && row.registration.disconnectedAt === null &&
        (!foreground || hasForegroundBinding(row)));
      if (!accountId || matches.length !== 1) throw new Error();
      const registration = matches[0].registration!;
      devices.add(deviceUuidSchema.parse(registration.deviceId));
      return {platform: platformCodes[platform], access_mode: 'PLATFORM_ACCOUNT' as const,
        connection_id: registration.connectionId, connection_version: registration.version};
    });
    if (devices.size > 1) throw new Error();
    return desktopExecutionCommandSchema.parse({action: 'START', humanConfirmed: true, requestId, profileVersionId: draft.profileId,
      strategyVersionId: receipt.strategy_version_id, configurationSha256: receipt.configuration_sha256, targets}) as DesktopStartCommand;
  } catch { throw new ServiceError('EXECUTION_BINDING_INVALID', '执行配置或账号登记尚未核实；请重新核对当前策略、设备与连接版本。'); }
}
