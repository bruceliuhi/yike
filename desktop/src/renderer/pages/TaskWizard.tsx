import { useEffect, useRef, useState } from "react";
import { ArrowClockwise, Plus, Sparkle, X } from "@phosphor-icons/react";
import { PlatformLabel } from "../components/Platform";
import { useApp } from "../app/context";
import { useAction, useLocalDraft, useResource } from "../app/hooks";
import {
  boundedRequest,
  RequestCancelled,
  SUGGESTION_TIMEOUT_MS,
} from "../app/boundedRequest";
import { useOperationLedger } from "../app/operationLedger";
import { useTaskDraft, useTaskLibrary } from "../app/taskDraft";
import {PlatformSearchTerms} from './tasks/PlatformSearchTerms';
import {PublicSourceSelector} from './tasks/PublicSourceSelector';
import {
  Badge,
  Button,
  Field,
  Modal,
  Notice,
  PageHeader,
  ResourceStatus,
  formatDate,
} from "../components/ui";
import { TermEditor } from "../components/TermEditor";
import {
  PLATFORMS,
  type Suggestion,
  type TaskDraft,
  type TaskRun,
} from "../domain/models";
import {
  applySuggestion,
  removeTerm,
  startBlockers,
  hasForegroundBinding,
  hasPublicSourceBinding,
  publicTaskScope,
  taskErrors,
  taskFingerprint,
} from "../domain/task";
import { errorMessage } from "../services/contracts";
import { routeHref } from "../domain/routes";
import {
  configurationHash,
  matchesCreatedTask,
  parseStartReceipt,
  startEntry,
  type TaskStartBinding,
} from "../domain/taskOperations";
import { PendingTaskStarts } from "./tasks/PendingTaskStarts";
import { useTaskScope } from "./tasks/useTaskScope";
import { TaskConfirmationSummary } from "./tasks/TaskConfirmationSummary";
import { StrategyConfirmationPanel } from "./tasks/StrategyConfirmationPanel";
import { StrategyExecutionLimits } from "./tasks/StrategyExecutionLimits";
import { validStrategyExecutionLimits } from "../domain/strategyExecutionLimits";
import { useStrategyConfirmation } from "./tasks/useStrategyConfirmation";
import { desktopStartCommand, useDesktopExecution } from "./tasks/useDesktopExecution";
import { DesktopExecutionRequests } from "./tasks/DesktopExecutionRequests";
import { DemandSettings, ResearchSettingsPanel } from "./tasks/ResearchSettings";
import { useUsageQuote } from "./tasks/useUsageQuote";
import { parseUsageQuote, usageQuoteCurrent, usageQuoteRequest, usageReservation } from "../domain/researchUsage";
import { scheduleContractBlocker, scheduleWindowLabel } from "../domain/schedule";
import {taskAccountLabel, scheduleRegionLabel} from './tasks/taskDisplayLabels';
import {useMonitorCollection} from './tasks/useMonitorCollection';
import {monitorCreateCommand} from '../domain/monitorCollection';
import { SearchSuggestionPanel } from "./tasks/SearchSuggestionPanel";
import { IndustryTaskStrategyEditor } from './tasks/IndustryTaskStrategyEditor';
import { adoptIndustryTaskStrategy } from '../domain/industryTaskStrategy';
import {nativeResearchStartCommand} from '../domain/nativeResearch';
import {DYNAMIC_RESEARCH_SOURCE} from '../../shared/dynamicResearch';
import {researchRuntimeCapabilitySchema,researchAllowsSelection} from '../../shared/researchRuntime';

export { matchesCreatedTask } from "../domain/taskOperations";

export function TaskWizardPage() {
  const { service, session, route, navigate, notify } = useApp();
  const [draft, setDraft] = useTaskDraft(
    session.userId,
    route.query.get("mode") === "monitor" ? "monitor" : "once",
    session.accountScope,
  );
  const [, setLibrary] = useTaskLibrary(session.userId, session.accountScope);
  const executionLimits = validStrategyExecutionLimits(draft.executionLimits);
  // Invalid/incomplete values never become suggested authority or leave this client.
  const strategy = useStrategyConfirmation(draft, executionLimits ?? { max_records: 0, max_runtime_seconds: 0 });
  const usage = useUsageQuote(draft, strategy);
  const desktopExecution = useDesktopExecution(strategy.prepared);
  const researchCapability = useResource(async signal => session.authenticated && draft.research && service.researchRuntime
    ? researchRuntimeCapabilitySchema.parse(await service.researchRuntime.capability(signal)) : null,
    [service,session.authenticated,session.userId,session.accountScope?.id,session.accountScope?.version,!!draft.research]);
  const nativeResearch = !!draft.research && service.execution?.researchContractVersion===1;
  const monitors = useMonitorCollection();
  const nativeMonitor = draft.mode === 'monitor' && monitors.available;
  const monitorReady = nativeMonitor && monitors.list?.supported === true;
  const strategyPreparationError = !executionLimits
    ? "请返回任务条件，使用推荐设置或在高级设置中调整处理范围。"
    : draft.research?.coverageProvenance
      ? "当前策略服务尚未支持补查来源。原草稿与溯源已保留，暂不能确认此策略。"
      : null;
  const [manualConditionOrigin, setManualConditionOrigin] = useLocalDraft<
    string | null
  >(
    `condition-origin.${session.userId || "guest"}.${draft.id}`,
    null,
    (value) => value === null || typeof value === "string",
  );
  const step =
    route.query.get("step") === "confirm"
      ? 3
      : route.query.get("step") === "connect"
        ? 2
        : 1;
  const profiles = useResource(
    () => (session.authenticated ? service.profiles() : Promise.resolve([])),
    [service, session.userId, session.authenticated, session.accountScope?.id, session.accountScope?.version],
  );
  const connections = useResource(
    () => service.connections(),
    [service, session.userId, session.authenticated, session.accountScope?.id, session.accountScope?.version],
  );
  const info = useResource(() => service.info(), [service, session.userId, session.authenticated, session.accountScope?.id, session.accountScope?.version]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [generating, setGenerating] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [preview, setPreview] = useState<Suggestion | null>(null);
  const requestGeneration = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const current = useRef(draft);
  current.current = draft;
  const lastSuggestion = useRef<string | null>(null);
  const action = useAction();
  const mounted = useRef(true);
  const [verified, setVerified] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [unknownStarts, setUnknownStarts] = useOperationLedger(
    "unknown-task-starts",
    session.userId,
  );
  const unresolvedAncestorIds = (draft.templateSourceDraftIds || []).filter(
    (id) => !!unknownStarts[id],
  );
  const resultUnknown =
    !!unknownStarts[draft.id] || unresolvedAncestorIds.length > 0 || nativeMonitor && monitors.pending.some(p=>p.action==='CREATE' && p.strategyVersionId===strategy.prepared?.strategy_version_id);
  const confirmed =
    profiles.data?.filter((p) => p.status === "CONFIRMED") || [];
  const selectedProfile = confirmed.find(
    (p) => p.id === draft.profileId && p.version === draft.profileVersion,
  );
  const conditionsOrigin = draft.suggestionProfile || manualConditionOrigin;
  const previousSuggestionProfile = profiles.data?.find(
    (p) => p.id === conditionsOrigin,
  );
  const staleConditions =
    !!conditionsOrigin &&
    conditionsOrigin !== draft.profileId &&
    (draft.terms.length > 0 || draft.exclusions.length > 0);
  const conditionsWarning = staleConditions
    ? `当前搜索条件仍来自「${
        previousSuggestionProfile
          ? `${previousSuggestionProfile.fields.service || "业务画像"} · v${previousSuggestionProfile.version}`
          : "历史画像（当前不可见）"
      }」，你的修改已保留。请按新画像复核，或重新生成后选择应用方式。`
    : "";
  const fingerprint = taskFingerprint(draft);
  const publicScope = publicTaskScope(draft,connections.data || []);
  const startScope = useTaskScope(JSON.stringify([fingerprint, draft.executionLimits,publicScope]));
  const reviewKey = strategy.available
    ? strategy.prepared ? JSON.stringify([fingerprint, draft.executionLimits,publicScope, strategy.prepared.request_id,
      strategy.prepared.strategy_version_id, strategy.prepared.configuration_sha256, strategy.prepared.profile_sha256]) : null
    : fingerprint;
  const reviewed = reviewKey !== null && verified === reviewKey;
  const blockers = startBlockers(
    draft,
    profiles.data || [],
    connections.data || [],
    info.data?.deviceReady === true,
    monitorReady,
    nativeResearch && researchAllowsSelection(researchCapability.data,draft.publicSource,draft.research?.sourcePlan),
  );
  if (!session.authenticated)
    blockers.unshift("请登录客户工作空间后启动任务。");
  if (strategy.available) {
    if (!service.execution) blockers.push("策略可先确认；签名执行接入尚未完成，当前不会启动采集。");
    if (service.execution && ((!nativeMonitor && draft.mode !== "once") || (draft.research && !nativeResearch)))
      blockers.push("当前签名执行仅支持无研究计费的单次任务；研究用量与监控调度接通前不会启动。");
    if (strategyPreparationError) blockers.push(strategyPreparationError);
    if (!strategy.confirmed) blockers.push("请准备策略快照、核对后主动确认本次策略。");
  }
  if (draft.mode === "monitor") {
    const scheduleBlocker = scheduleContractBlocker(draft.schedule, monitorReady ? 1 : service.taskOperations?.scheduleContractVersion);
    if (scheduleBlocker) blockers.push(scheduleBlocker);
    if(nativeMonitor && !monitorReady) blockers.push('请等待本机监控能力检查；未接通时只可保存草稿。');
    if(nativeMonitor && monitors.list?.plans.some(p=>p.strategyVersionId===strategy.prepared?.strategy_version_id)) blockers.push('该策略已有监控计划，请前往监控任务查看或接管。');
  }
  if (draft.research) {
    if (!service.researchUsage || (nativeResearch ? !researchCapability.data : service.taskOperations?.researchContractVersion !== 1))
      blockers.push("研究用量服务尚未接通，当前可以保存草稿。");
    else if (!usage.valid) blockers.push("请先估算当前配置的搜贝用量，再确认启动。");
    if(nativeResearch && (draft.mode!=='once' || draft.platforms.length!==1 || draft.platforms[0]!=='web' || !researchAllowsSelection(researchCapability.data,draft.publicSource,draft.research?.sourcePlan)))
      blockers.push('所选板块尚未核实研究能力；当前仅支持已接通V2EX板块的单次索引研究，不含其他平台或持续调度。');
  }
  const update = (patch: Partial<TaskDraft>) => {
    setDraft((old) => ({
      ...old,
      ...patch,
      revision: old.revision + 1,
      savedAt: null,
    }));
    setVerified(null);
    setErrors({});
  };
  const save = () => {
    requestGeneration.current++;
    controller.current?.abort();
    setGenerating(false);
    const snapshot = { ...current.current, savedAt: new Date().toISOString() };
    setDraft(snapshot);
    setLibrary((old) => [snapshot, ...old.filter((t) => t.id !== snapshot.id)]);
    notify(
      resultUnknown
        ? "任务草稿已保存；原启动结果仍待核对。"
        : "任务草稿已保存在本机会话中，尚未启动。",
      "success",
    );
  };
  const stepPath = (next: number) =>
    "/tasks/new?" +
    new URLSearchParams({
      ...(next === 1 ? {} : { step: next === 2 ? "connect" : "confirm" }),
      ...(draft.mode === "monitor" ? { mode: "monitor" } : {}),
    }).toString();
  const changeStep = (next: number) => {
    if (next > step) {
      const validation = taskErrors(current.current);
      if (Object.keys(validation).length) {
        setErrors(validation);
        notify("请先检查任务条件。", "error");
        return;
      }
    }
    navigate(stepPath(next));
  };
  useEffect(() => {
    if (!draft.profileId && confirmed.length) {
      setDraft((old) =>
        old.profileId
          ? old
          : {
              ...old,
              profileId: confirmed[0].id,
              profileVersion: confirmed[0].version,
              revision: old.revision + 1,
            },
      );
    }
  }, [profiles.data]);
  useEffect(() => {
    if (
      route.query.get("mode") === "monitor" &&
      current.current.mode !== "monitor"
    )
      setDraft((old) => ({
        ...old,
        mode: "monitor",
        revision: old.revision + 1,
      }));
  }, [route.query.get("mode")]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestGeneration.current++;
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    requestGeneration.current++;
    controller.current?.abort();
    setGenerating(false);
    setPreview(null);
    setSuggestionError("");
  }, [draft.id, draft.profileId, draft.profileVersion, session.userId, session.accountScope?.id, session.accountScope?.version, step]);
  const cancelSuggestion = () => {
    requestGeneration.current++;
    controller.current?.abort();
    setGenerating(false);
    setPreview(null);
    setSuggestionError("已取消建议生成，现有条件已保留，可继续手工填写。");
  };
  const generate = async (automatic = false) => {
    const snapshot = current.current;
    if (!snapshot.profileId) {
      setSuggestionError(
        "确认业务画像后可生成搜索建议，也可以先手工添加关键词。",
      );
      return;
    }
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const generation = ++requestGeneration.current;
    const requestId = crypto.randomUUID();
    setGenerating(true);
    setSuggestionError("");
    try {
      const result = await boundedRequest(
        (signal) => service.suggest(snapshot.profileId, requestId, signal),
        {
          signal: abort.signal,
          timeoutMs: SUGGESTION_TIMEOUT_MS,
          timeoutMessage:
            "搜索建议生成超时，现有条件已保留。可重试或继续手工填写。",
        },
      );
      if (
        generation !== requestGeneration.current ||
        current.current.id !== snapshot.id ||
        current.current.profileId !== snapshot.profileId ||
        current.current.profileVersion !== snapshot.profileVersion
      )
        return;
      if (
        result.profileId !== snapshot.profileId ||
        result.requestId !== requestId
      )
        throw new Error("搜索建议与当前画像不一致，请重新生成。");
      if (
        !Array.isArray(result.keywords) ||
        !Array.isArray(result.exclusions) ||
        [...result.keywords, ...result.exclusions].some(
          (v) => typeof v !== "string" || !v.trim() || v.length > 80,
        ) ||
        result.keywords.length > 20 ||
        result.exclusions.length > 20
      )
        throw new Error("搜索建议格式不完整，请重试或手工添加。");
      if (
        automatic &&
        current.current.revision === snapshot.revision &&
        !snapshot.terms.length &&
        !snapshot.exclusions.length
      ) {
        setDraft((old) => applySuggestion(old, result, "append"));
      } else setPreview(result);
    } catch (error) {
      if (
        generation === requestGeneration.current &&
        !(error instanceof RequestCancelled) &&
        !(error instanceof DOMException && error.name === "AbortError")
      )
        setSuggestionError(errorMessage(error));
    } finally {
      if (generation === requestGeneration.current) setGenerating(false);
    }
  };
  useEffect(() => {
    if (
      !service.searchSuggestions &&
      selectedProfile &&
      step === 1 &&
      !draft.savedAt &&
      !draft.templateSourceDraftIds?.length &&
      !draft.research?.provenance &&
      !draft.suggestionProfile &&
      lastSuggestion.current !==
        `${draft.id}:${selectedProfile.id}:${selectedProfile.version}` &&
      !draft.terms.length &&
      !draft.exclusions.length &&
      !draft.removed.length
    ) {
      lastSuggestion.current = `${draft.id}:${selectedProfile.id}:${selectedProfile.version}`;
      void generate(true);
    }
  }, [draft.id, selectedProfile?.id, selectedProfile?.version, step]);
  const applyControlledSuggestion = (
    receipt: import("../../shared/searchSuggestions").SuggestionReceipt,
    mode: "append" | "replace_unedited",
  ) => {
    if (!receipt.result) return false;
    const next = applySuggestion(current.current, {
      profileId: receipt.profile_version_id,
      requestId: receipt.request_id,
      keywords: receipt.result.keywords,
      exclusions: receipt.result.exclusions,
    }, mode);
    if (next.terms.length > 20 || next.exclusions.length > 20) {
      setSuggestionError("合并后词项超过20个，请先删除部分词项再合并。");
      return false;
    }
    setDraft(next);
    setManualConditionOrigin(null);
    setSuggestionError("");
    setVerified(null);
    return true;
  };
  const applyControlledStrategy = (receipt: import('../../shared/searchSuggestions').SuggestionReceipt) => {
    const next=adoptIndustryTaskStrategy(current.current,receipt);
    if(next===current.current)return false;
    setDraft(next);setVerified(null);setErrors({});
    return true;
  };
  const acceptSuggestion = (mode: "append" | "replace_unedited") => {
    if (!preview) return;
    const next = applySuggestion(current.current, preview, mode);
    if (next.terms.length > 20 || next.exclusions.length > 20) {
      setSuggestionError("合并后词项超过20个，请先删除部分词项再合并。");
      setPreview(null);
      return;
    }
    setDraft(next);
    setManualConditionOrigin(null);
    setPreview(null);
    setSuggestionError("");
    setVerified(null);
  };
  const validateDesktopStart = async (requestId: string) => {
    if (!session.authenticated || !reviewed || !strategy.confirmed || !strategy.prepared ||
        !service.execution || strategyPreparationError || resultUnknown || !startScope.current())
      throw new Error("请核对当前草稿及已确认策略，尚未启动。");
    const snapshot = structuredClone(current.current);
    const prepared = structuredClone(strategy.prepared);
    if (snapshot.mode !== "once" || snapshot.research)
      throw new Error("当前执行协议尚未接通研究计费与监控调度，尚未启动。");
    const [freshProfiles, freshConnections, freshInfo] = await boundedRequest(() => Promise.all([
      service.profiles(), service.connections(), service.info(),
    ]), {timeoutMessage: "启动条件检查超时，尚未创建任务，请重新检查。"});
    if (!startScope.current()) throw new RequestCancelled();
    if(publicTaskScope(snapshot,freshConnections)!==publicScope)
      throw new Error('公开读取范围或执行设备已变化，请重新载入并核对，尚未启动。');
    // A selected web account must also have its own checked runtime capability.
    const capabilityConnections = snapshot.accounts.web ? freshConnections.filter(row =>
      row.platform !== "web" || row.accountId === snapshot.accounts.web) : freshConnections;
    const reasons = startBlockers(snapshot, freshProfiles, capabilityConnections, freshInfo.deviceReady === true);
    if (reasons.length) throw new Error(reasons.join(" "));
    if (!await strategy.recheck() || !startScope.current())
      throw new Error("当前策略尚未重新核实，尚未启动。");
    return desktopStartCommand(snapshot, prepared, freshConnections, requestId);
  };
  const start = async () => {
    if (
      !session.authenticated ||
      starting ||
      resultUnknown ||
      !reviewed ||
      (strategy.available && (!service.execution || (!nativeMonitor && (desktopExecution.blocksStart || desktopExecution.busy)) || monitors.busy || blockers.length > 0))
    )
      return;
    const snapshot = structuredClone(current.current);
    const usageSnapshot = usage.quote;
    setStarting(true);
    await action.run(async () => {
      if(nativeMonitor){
        if(!monitorReady || !strategy.confirmed || !strategy.prepared || !strategy.view || !await strategy.recheck() || !startScope.current())throw new Error('请重新核对当前监控策略。');
        const [freshProfiles,freshConnections,freshInfo]=await boundedRequest(()=>Promise.all([service.profiles(),service.connections(),service.info()]),{timeoutMessage:'监控启动条件检查超时，尚未创建计划。'});
        if(!startScope.current())throw new RequestCancelled();
        const reasons=startBlockers(snapshot,freshProfiles,freshConnections,freshInfo.deviceReady===true,true);
        if(reasons.length)throw new Error(reasons.join(' '));
        const result=await monitors.execute(monitorCreateCommand(snapshot,strategy.prepared,strategy.view,freshConnections,crypto.randomUUID()));
        if(!startScope.current())return;
        if(result?.state==='RECORDED')navigate(`/monitors/${result.plan.planId}`);
        return;
      }
      if (strategy.available) {
        if(nativeResearch){
          if(!usageSnapshot || !strategy.prepared || !strategy.confirmed || !service.researchRuntime || !reviewed)
            throw new Error('请重新确认策略与本次研究上限。');
          const prepared=structuredClone(strategy.prepared);
          const [freshProfiles,freshConnections,freshInfo]=await boundedRequest(()=>Promise.all([
            service.profiles(),service.connections(),service.info(),
          ]),{timeoutMessage:'研究启动检查超时，尚未创建任务。'});
          if(!startScope.current())throw new RequestCancelled();
          if(publicTaskScope(snapshot,freshConnections)!==publicScope)throw new Error('公开读取范围或执行设备已变化，请重新核对。');
          const reasons=startBlockers(snapshot,freshProfiles,freshConnections,freshInfo.deviceReady===true,false,true);
          if(reasons.length)throw new Error(reasons.join(' '));
          const freshResearch=researchRuntimeCapabilitySchema.parse(await boundedRequest(signal=>service.researchRuntime!.capability(signal),
            {timeoutMessage:'研究执行能力尚未核实，未创建任务。'}));
          if(!researchAllowsSelection(freshResearch,snapshot.publicSource,snapshot.research?.sourcePlan))throw new Error('所选板块研究能力已变化，请重新核对；未创建任务。');
          if(!await strategy.recheck() || !startScope.current())throw new Error('当前研究策略尚未重新核实。');
          const command=await nativeResearchStartCommand(snapshot,prepared,freshConnections,session,usageSnapshot,crypto.randomUUID(),freshResearch);
          if(!startScope.current())throw new RequestCancelled();
        await desktopExecution.startResearch(command,receipt=>{
          if(startScope.current())navigate(`/collection?task=${receipt.execution.task_id}`);
        });
          return;
        }
        await desktopExecution.start(await validateDesktopStart(crypto.randomUUID()));
        return;
      }
      // Recheck live execution prerequisites immediately before creating one task.
      const [freshProfiles, freshConnections, freshInfo] = await boundedRequest(
        () =>
          Promise.all([
            service.profiles(),
            service.connections(),
            service.info(),
          ]),
        { timeoutMessage: "启动条件检查超时，尚未创建任务，请重新检查。" },
      );
      if (!startScope.current()) return;
      const changed =
        taskFingerprint(current.current) !== taskFingerprint(snapshot);
      const reasons = startBlockers(
        snapshot,
        freshProfiles,
        freshConnections,
        freshInfo.deviceReady === true,
      );
      if (snapshot.mode === "monitor") {
        const scheduleBlocker = scheduleContractBlocker(snapshot.schedule, service.taskOperations?.scheduleContractVersion);
        if (scheduleBlocker) reasons.push(scheduleBlocker);
      }
      if (changed || reasons.length) {
        setVerified(null);
        throw new Error(
          changed ? "任务配置已经变化，请重新核对。" : reasons.join(" "),
        );
      }
      const requestId = `task:${snapshot.id}:${snapshot.revision}`;
      const binding: TaskStartBinding = {
        requestId,
        draftId: snapshot.id,
        revision: snapshot.revision,
        configurationHash: await configurationHash(snapshot),
        mode: snapshot.mode,
        ...(snapshot.research && usageSnapshot ? { usageReservation: usageReservation(usageSnapshot) } : {}),
      };
      if (snapshot.research) {
        if (!service.researchUsage || service.taskOperations?.researchContractVersion !== 1 || !usageQuoteCurrent(usageSnapshot, snapshot, session))
          throw new Error("研究用量尚未确认或估算已经过期，请重新核对；尚未启动。");
        const expected = usageQuoteRequest(snapshot, session, binding.configurationHash);
        parseUsageQuote(usageSnapshot, { ...expected, requestId: usageSnapshot!.requestId });
      }
      if (!startScope.current()) return;
      if (snapshot.mode === "monitor") {
        const scheduleBlocker = scheduleContractBlocker(snapshot.schedule, service.taskOperations?.scheduleContractVersion);
        if (scheduleBlocker) throw new Error(scheduleBlocker);
      }
      const stored = startEntry(binding);
      setUnknownStarts((old) => {
        if (
          [snapshot.id, ...(snapshot.templateSourceDraftIds || [])].some(
            (id) => !!old[id],
          )
        )
          throw new Error("该任务已有启动请求待确认，当前不会重复创建。");
        return { ...old, [snapshot.id]: stored };
      });
      let run;
      try {
        if (service.taskOperations) {
          const receipt = parseStartReceipt(
            await boundedRequest(
              () => service.taskOperations!.start(snapshot, binding, snapshot.research ? usageSnapshot! : undefined),
              {
                timeoutMessage:
                  "启动等待超时，结果尚未确认，请核对原启动结果。",
              },
            ),
            binding,
          );
          if (!startScope.current()) return;
          if (receipt.status === "REJECTED") {
            setUnknownStarts((old) => {
              const next = { ...old };
              if (next[snapshot.id] === stored) delete next[snapshot.id];
              return next;
            });
            if (startScope.current()) {
              setVerified(null);
              setDraft((old) =>
                old.id === snapshot.id
                  ? { ...old, revision: old.revision + 1, savedAt: null }
                  : old,
              );
            }
            throw new Error(
              receipt.message || "原请求已确认未创建任务，请重新检查配置。",
            );
          }
          if (receipt.status !== "ACCEPTED")
            throw new Error("启动结果尚未确认，请核对原请求，勿重新提交。");
          run = receipt.run;
        } else {
          run = await boundedRequest(
            () => service.startTask(snapshot, requestId),
            {
              timeoutMessage: "启动等待超时，结果尚未确认，请核对原启动结果。",
            },
          );
        }
      } catch (error) {
        const code =
          error && typeof error === "object" && "code" in error
            ? String(error.code)
            : "";
        if (
          !service.taskOperations &&
          [
            "CAPABILITY_UNAVAILABLE",
            "INVALID_REQUEST",
            "FORBIDDEN",
            "UNAUTHORIZED",
            "VALIDATION_ERROR",
          ].includes(code)
        )
          setUnknownStarts((old) => {
            const next = { ...old };
            delete next[snapshot.id];
            return next;
          });
        throw error;
      }
      if (!matchesCreatedTask(run, snapshot))
        throw new Error(
          "任务返回结果与本次配置不一致，创建结果尚未确认。请核对原请求，勿重新提交。",
        );
      setUnknownStarts((old) => {
        const next = { ...old };
        delete next[snapshot.id];
        return next;
      });
      if (!startScope.current()) return;
      setLibrary((old) => old.filter((t) => t.id !== snapshot.id));
      notify("任务已创建，运行状态以任务详情为准。", "success");
      navigate(
        snapshot.mode === "monitor"
          ? `/monitors/${encodeURIComponent(run.id)}`
          : "/collection",
      );
    });
    if (mounted.current) setStarting(false);
  };
  const platformLabel = (id: string) =>
    PLATFORMS.find((p) => p.id === id)?.name || id;
  return (
    <>
      <PageHeader
        title={
          step === 3
            ? "确认启动任务"
            : draft.mode === "monitor"
              ? "新建监控任务"
              : "新建获客任务"
        }
        description={
          resultUnknown
            ? "启动结果待确认"
            : draft.savedAt
              ? "本机草稿 · 未启动"
              : "配置任务条件，确认后再启动。"
        }
      />
      <div className="wizard-steps" aria-label="任务步骤">
        {["任务条件", "平台连接", "确认启动"].map((label, i) => (
          <div
            className={`wizard-step ${step === i + 1 ? "active" : ""}`}
            aria-current={step === i + 1 ? "step" : undefined}
            key={label}
          >
            <span className={`step-number ${step === i + 1 ? "current" : ""}`}>
              {i + 1}
            </span>
            {label}
          </div>
        ))}
      </div>
      {conditionsWarning && <Notice tone="warning">{conditionsWarning}</Notice>}
      {step === 1 ? (
        <div className="task-layout">
          <div
            className={`task-form ${draft.research ? "research-form" : ""} ${draft.mode === "monitor" ? "monitor-form" : ""}`}
          >
            <section className="form-section">
              <h2>基本信息</h2>
              <Field
                label="任务名称"
                required
                className="horizontal-field"
                error={errors.name}
              >
                <input
                  aria-label="任务名称"
                  value={draft.name}
                  maxLength={60}
                  placeholder="给这个任务起一个便于识别的名称"
                  onChange={(e) => update({ name: e.target.value })}
                />
              </Field>
              <Field
                label="业务画像"
                className="horizontal-field"
                hint={
                  selectedProfile
                    ? "已确认业务画像"
                    : "选择真实已确认画像，或先保存本机草稿。"
                }
              >
                <select
                  aria-label="业务画像"
                  value={draft.profileId}
                  disabled={profiles.loading}
                  onChange={(e) => {
                    const selected = confirmed.find(
                      (p) => p.id === e.target.value,
                    );
                    if (
                      (draft.terms.length || draft.exclusions.length) &&
                      !conditionsOrigin
                    )
                      setManualConditionOrigin(draft.profileId || null);
                    update({
                      profileId: selected?.id || "",
                      profileVersion: selected?.version || null,
                    });
                  }}
                >
                  <option value="">选择业务画像</option>
                  {confirmed.map((p) => (
                    <option value={p.id} key={p.id}>
                      {p.businessName || p.fields.service || "业务画像"} · v{p.version}
                    </option>
                  ))}
                </select>
              </Field>
              {profiles.error && (
                <Notice
                  tone="warning"
                  action={
                    <Button variant="ghost" onClick={profiles.reload}>
                      重试
                    </Button>
                  }
                >
                  {profiles.error}
                </Notice>
              )}
            </section>
            <DemandSettings value={draft.research} onChange={research => update({ research })} />
            <section className="form-section">
              {service.searchSuggestions ? <SearchSuggestionPanel
                service={service.searchSuggestions}
                scope={session.authenticated && session.userId && session.accountScope ? {
                  userId: session.userId,
                  accountScopeId: session.accountScope.id,
                  accountScopeVersion: session.accountScope.version,
                } : null}
                draftId={draft.id}
                draftRevision={draft.revision}
                profileVersionId={draft.profileId}
                profileConfirmed={!!selectedProfile}
                hasTerms={draft.terms.length > 0}
                onApply={applyControlledSuggestion}
                onApplyStrategy={applyControlledStrategy}
                hasStrategy={!!draft.industryStrategy}
              /> : <div className="search-heading">
                <div>
                  <h2>搜索条件</h2>
                  <Badge tone="blue">
                    <Sparkle size={12} /> AI 建议
                  </Badge>
                </div>
                {generating ? (
                  <Button variant="ghost" onClick={cancelSuggestion}>
                    <X />
                    取消生成
                  </Button>
                ) : (
                  <Button variant="ghost" onClick={() => void generate()}>
                    <ArrowClockwise />
                    {draft.terms.length ? "重新生成" : "生成建议"}
                  </Button>
                )}
              </div>}
              <Field
                label="搜索关键词"
                className="horizontal-field"
                error={errors.terms}
                hint={
                  generating
                    ? "正在根据画像生成，当前编辑不会被覆盖。"
                    : staleConditions
                      ? "沿用旧画像条件，请按当前画像复核。"
                      : draft.suggestionProfile
                        ? "建议基于所选画像，可自由修改。"
                        : "确认画像后自动建议，也可手工添加。"
                }
              >
                <TermEditor
                  label="搜索关键词"
                  terms={draft.terms}
                  onChange={(terms) => update({ terms })}
                  onRemove={(id) =>
                    setDraft((old) => removeTerm(old, "terms", id))
                  }
                />
              </Field>
              <Field label="排除词" className="horizontal-field" hint="结果返回本机后再过滤；评论只匹配评论自身正文，不匹配父帖。">
                <TermEditor
                  label="排除词"
                  terms={draft.exclusions}
                  neutral
                  onChange={(exclusions) => update({ exclusions })}
                  onRemove={(id) =>
                    setDraft((old) => removeTerm(old, "exclusions", id))
                  }
                />
              </Field>
              {suggestionError && (
                <Notice tone="warning">{suggestionError}</Notice>
              )}
              {errors.conflicts && (
                <Notice tone="error">{errors.conflicts}</Notice>
              )}
              <PlatformSearchTerms draft={draft} onChange={platformTerms=>update({platformTerms})}/>
            </section>
            <IndustryTaskStrategyEditor value={draft.industryStrategy} profileId={draft.profileId}
              onChange={industryStrategy=>update({industryStrategy})}/>
            <section className="form-section">
              <h2>采集范围</h2>
              <Field
                label="选择平台"
                className="horizontal-field"
                error={errors.platforms}
              >
                <div className="platform-choices">
                  {PLATFORMS.map((p) => {
                    const status = !draft.research ? ""
                      : p.id === "web" ? "无需账号"
                      : connections.loading ? "读取中"
                      : connections.error ? "读取失败"
                      : connections.data?.some(c => c.platform === p.id && c.status === "CONNECTED") ? "已连接"
                      : connections.data?.some(c => c.platform === p.id && c.status === "UNVERIFIED") ? "待核验"
                      : "待连接";
                    return (
                    <label key={p.id}>
                      <input
                        type="checkbox"
                        aria-label={status ? `${p.name} ${status}` : p.name}
                        checked={draft.platforms.includes(p.id)}
                        onChange={(e) =>
                          update({
                            platforms: e.target.checked
                              ? [...draft.platforms, p.id]
                              : draft.platforms.filter((id) => id !== p.id),
                          })
                        }
                      />
                      <PlatformLabel platform={p.id} size={18} />
                      {status && <small className="muted">{status}</small>}
                    </label>
                    );
                  })}
                </div>
              </Field>
              <Field label="来源范围" className="horizontal-field">
                <div className="radio-group">
                  <label>
                    <input
                      type="radio"
                      name="source"
                      checked={draft.source === "search"}
                      onChange={() => update({ source: "search" })}
                    />
                    关键词搜索
                  </label>
                  <label>
                    <input
                      type="radio"
                      name="source"
                      checked={draft.source === "links"}
                      onChange={() => update({ source: "links" })}
                    />
                    指定内容链接
                  </label>
                </div>
              </Field>
              {draft.source === "links" && (
                <Field
                  label="内容链接"
                  className="horizontal-field"
                  error={errors.links}
                >
                  <textarea
                    aria-label="内容链接"
                    rows={4}
                    value={draft.links}
                    placeholder="每行一个公开内容链接"
                    onChange={(e) => update({ links: e.target.value })}
                  />
                </Field>
              )}
            </section>
            <section className="form-section">
              <h2>运行设置</h2>
              <Field label="运行方式" className="horizontal-field">
                <div className="radio-group">
                  <label>
                    <input
                      type="radio"
                      name="mode"
                      checked={draft.mode === "once"}
                      onChange={() => update({ mode: "once" })}
                    />
                    单次采集
                  </label>
                  <label>
                    <input
                      type="radio"
                      name="mode"
                      checked={draft.mode === "monitor"}
                      onChange={() => update({ mode: "monitor" })}
                    />
                    持续监控
                  </label>
                </div>
              </Field>
              {draft.mode === "monitor" && (
                <div className="schedule-fields">
                  <Field
                    label="执行频率"
                    className="horizontal-field"
                    error={errors.schedule}
                  >
                    <div className="radio-group">
                      <label>
                        <input
                          type="radio"
                          name="schedule"
                          checked={draft.schedule.kind === "daily"}
                          onChange={() =>
                            update({
                              schedule: { ...draft.schedule, kind: "daily" },
                            })
                          }
                        />
                        每日定时
                      </label>
                      <label>
                        <input
                          type="radio"
                          name="schedule"
                          checked={draft.schedule.kind === "interval"}
                          onChange={() =>
                            update({
                              schedule: { ...draft.schedule, kind: "interval" },
                            })
                          }
                        />
                        固定间隔
                      </label>
                    </div>
                  </Field>
                  {draft.schedule.kind === "daily" ? (
                    <Field label="执行时间" className="horizontal-field">
                      <div className="time-list">
                        {draft.schedule.times.map((time, i) => (
                          <div key={i} className="time-entry">
                            <input
                              type="time"
                              aria-label={`执行时间${i + 1}`}
                              value={time}
                              onChange={(e) =>
                                update({
                                  schedule: {
                                    ...draft.schedule,
                                    times: draft.schedule.times.map((t, n) =>
                                      i === n ? e.target.value : t,
                                    ),
                                  },
                                })
                              }
                            />
                            <button
                              className="icon-button"
                              aria-label={`删除执行时间${i + 1}`}
                              disabled={draft.schedule.times.length === 1}
                              onClick={() =>
                                update({
                                  schedule: {
                                    ...draft.schedule,
                                    times: draft.schedule.times.filter(
                                      (_, n) => n !== i,
                                    ),
                                  },
                                })
                              }
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ))}
                        <Button
                          variant="ghost"
                          disabled={draft.schedule.times.length >= 6}
                          onClick={() =>
                            update({
                              schedule: {
                                ...draft.schedule,
                                times: [...draft.schedule.times, "14:00"],
                              },
                            })
                          }
                        >
                          <Plus />
                          添加时间
                        </Button>
                      </div>
                    </Field>
                  ) : (
                    <>
                      <Field label="间隔" className="horizontal-field">
                        <div className="schedule-inline">
                          每
                          <input
                            aria-label="间隔小时"
                            type="number"
                            min={1}
                            max={168}
                            value={draft.schedule.interval}
                            onChange={(e) =>
                              update({
                                schedule: {
                                  ...draft.schedule,
                                  interval: Number(e.target.value),
                                },
                              })
                            }
                          />
                          小时
                        </div>
                      </Field>
                      <Field label="执行窗口" className="horizontal-field">
                        <div className="schedule-inline">
                          <input
                            type="time"
                            aria-label="执行窗口开始"
                            value={draft.schedule.start}
                            onChange={(e) =>
                              update({
                                schedule: {
                                  ...draft.schedule,
                                  start: e.target.value,
                                },
                              })
                            }
                          />
                          至
                          <input
                            type="time"
                            aria-label="执行窗口结束"
                            value={draft.schedule.end}
                            onChange={(e) =>
                              update({
                                schedule: {
                                  ...draft.schedule,
                                  end: e.target.value,
                                },
                              })
                            }
                          />
                        </div>
                      </Field>
                    </>
                  )}
                  <Field
                    label="时区"
                    className="horizontal-field"
                    error={errors.timezone}
                  >
                    <select
                      aria-label="执行时区"
                      value={draft.schedule.timezone}
                      onChange={(e) =>
                        update({
                          schedule: {
                            ...draft.schedule,
                            timezone: e.target.value,
                          },
                        })
                      }
                    >
                      {[
                        ...new Set([
                          draft.schedule.timezone,
                          "Asia/Shanghai",
                          "Asia/Hong_Kong",
                          "Asia/Singapore",
                          "Europe/London",
                          "America/New_York",
                          "UTC",
                        ]),
                      ].map((t) => (
                        <option key={t} value={t}>{scheduleRegionLabel(t)}</option>
                      ))}
                    </select>
                  </Field>
                  <div aria-label="监控日程规则">
                    {draft.schedule.kind === "interval" && (
                      <p className="field-hint">任务窗口：{scheduleWindowLabel(draft.schedule)}</p>
                    )}
                    <p className="field-hint">离线错过的计划不补跑，恢复在线后从下次计划继续。</p>
                    {draft.schedule.policyVersion === undefined && (
                      <Button variant="ghost" onClick={() => update({
                        schedule: { ...draft.schedule, policyVersion: 1 },
                      })}>
                        采用当前日程规则
                      </Button>
                    )}
                    <p className="field-hint">执行时间仍受所选平台能力和设备在线状态限制。</p>
                  </div>
                </div>
              )}
            </section>
          </div>
          <aside className="task-aside">
            {strategy.available && <StrategyExecutionLimits value={draft.executionLimits} onChange={executionLimits => update({ executionLimits })} />}
            <ResearchSettingsPanel value={draft.research} onChange={research => update({ research })} quote={usage.quote} busy={usage.busy} error={usage.error} onEstimate={() => void usage.estimate()} onCancel={usage.cancel} onPreview={() => changeStep(3)} />
            {!draft.research && <>
            <div className="section-heading">
              <h2>平台连接状态</h2>
              <span className="muted text-small">按实际连接检查</span>
            </div>
            <div className="platform-status-list">
              {PLATFORMS.map((p) => {
                const connection = connections.data?.find(
                  (c) => c.platform === p.id,
                );
                return (
                  <div className="platform-status-row" key={p.id}>
                    <span>
                      <PlatformLabel platform={p.id} size={21} />
                    </span>
                    <Badge
                      tone={
                        connection?.status === "CONNECTED" ? "green" : "neutral"
                      }
                    >
                      {connection?.status === "CONNECTED"
                        ? (hasPublicSourceBinding(connection) ? '匿名范围已就绪' : '已连接')
                        : connection?.status === "EXPIRED"
                          ? "登录已失效"
                          : connection?.status === "UNVERIFIED"
                            ? "待核验"
                          : p.id === "web"
                            ? "范围待确认"
                            : connections.loading
                              ? "正在读取"
                              : "待连接"}
                    </Badge>
                  </div>
                );
              })}
            </div>
            <Notice>下一步完成平台连接。</Notice>
            </>}
            {connections.error && (
              <p className="field-hint">{connections.error}</p>
            )}
            <div className="task-footer">
              <Button onClick={save}>保存草稿</Button>
              <Button variant="primary" onClick={() => changeStep(2)}>
                下一步：连接平台
              </Button>
            </div>
          </aside>
        </div>
      ) : step === 2 ? (
        <div className="confirmation-layout">
          <h2>为所选平台配置执行账号</h2>
          <p className="page-description">
            返回修改会保留所有搜索条件和运行设置。
          </p>
          <ResourceStatus
            loading={connections.loading}
            error={connections.error}
            onRetry={connections.reload}
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>平台</th>
                  <th>执行账号 / 范围</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {draft.platforms.map((id) => (
                  <tr key={id}>
                    <td>
                      <PlatformLabel platform={id} size={18} />
                    </td>
                    <td>
                      {id === "web" ? (
                        <PublicSourceSelector draft={draft} connections={connections.data??[]} researchCapability={researchCapability.data} onChange={publicSource=>{
                          if(publicSource===draft.publicSource)return;
                          if(!draft.research||(publicSource!==DYNAMIC_RESEARCH_SOURCE&&draft.publicSource!==DYNAMIC_RESEARCH_SOURCE)){update({publicSource});return;}
                          const {sourcePlan,dynamicScope,provenance,coverageProvenance,...research}=draft.research;
                          update({publicSource,platformTerms:undefined,research:publicSource===DYNAMIC_RESEARCH_SOURCE?{...research,
                            dynamicScope:{version:1,maxAgeDays:60,timezone:'Asia/Shanghai'},limits:{sources:20,minutes:15,modelCalls:20}}:research});
                        }}
                          onPlanChange={(publicSource,sourcePlan)=>{if(!draft.research)return;const {sourcePlan:previous,...research}=draft.research;
                            update({publicSource,research:{...research,...(sourcePlan?{sourcePlan}:{})}});}}/>
                      ) : (
                        <select
                          aria-label={`${platformLabel(id)}执行账号`}
                          value={draft.accounts[id] || ""}
                          onChange={(e) =>
                            update({
                              accounts: {
                                ...draft.accounts,
                                [id]: e.target.value,
                              },
                            })
                          }
                        >
                          <option value="">选择已连接账号</option>
                          {connections.data
                            ?.filter(
                              (c) =>
                                c.platform === id && c.status === "CONNECTED" && (!c.registration || hasForegroundBinding(c)),
                            )
                            .map((c) => (
                              <option key={c.registration?.connectionId || c.accountId} value={c.accountId}>
                                {taskAccountLabel(c, connections.data || [])}
                              </option>
                            ))}
                          {connections.data?.filter(c => c.platform === id && c.registration && !hasForegroundBinding(c)).map((c) => (
                            <option key={c.registration!.connectionId} value={`registered:${c.registration!.connectionId}`} disabled>
                              {taskAccountLabel(c, connections.data || [])}（当前不可用）
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td>
                      <Button
                        variant="ghost"
                        onClick={() =>
                          navigate(
                            id === "web"
                              ? `/connections?returnTo=${encodeURIComponent(routeHref(route))}`
                              : `/connections?connect=${id}&returnTo=${encodeURIComponent(routeHref(route))}`,
                          )
                        }
                      >
                        {id === "web" ? "查看范围" : "连接账号"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!draft.platforms.length && (
            <Notice tone="warning">请返回任务条件选择至少一个平台。</Notice>
          )}
          <section className="form-section">
            <div className="section-heading">
              <h2>采集准备</h2>
              <Badge tone={info.data?.deviceReady ? "green" : "neutral"}>
                {info.data?.deviceReady ? "执行服务已就绪" : "尚未就绪"}
              </Badge>
            </div>
            <p className="muted">
              请检查所选平台的连接及服务状态；启动前会再次核对。
            </p>
            <Button variant="ghost" onClick={() => void info.reload()}>
              重新检查
            </Button>
          </section>
          <div className="task-footer">
            <Button onClick={() => changeStep(1)}>上一步</Button>
            <Button onClick={save}>保存草稿</Button>
            <Button variant="primary" onClick={() => changeStep(3)}>
              下一步：确认任务
            </Button>
          </div>
        </div>
      ) : (
        <div className="confirmation-layout task-confirmation-page">
          <TaskConfirmationSummary
            draft={draft}
            usage={usage.quote}
            profile={selectedProfile}
            connections={connections.data || []}
            deviceReady={!!info.data?.deviceReady}
            disabled={starting}
            onEdit={() => changeStep(1)}
          />
          <StrategyConfirmationPanel strategy={strategy} reviewed={reviewed} onReviewedChange={checked => setVerified(checked ? reviewKey : null)}
            disabled={starting} preparationError={strategyPreparationError} />
          {draft.research && <Notice action={<Button disabled={starting} onClick={usage.busy ? usage.cancel : () => void usage.estimate()}>{usage.busy ? "取消估算" : "重新估算"}</Button>}>
            {usage.error || (usage.quote ? usage.quote.strategyBinding
              ? `资源上限估算 ${usage.quote.estimatedSoubei} 搜贝，最多 ${usage.quote.maxSoubei} 搜贝；未预留，也不是实际消耗预测。`
              : `预计 ${usage.quote.estimatedSoubei} 搜贝，最多 ${usage.quote.maxSoubei} 搜贝；确认后按本次规则执行。`
              : "请完成用量估算，再核对配置并启动。")}
          </Notice>}
          {blockers.length > 0 && (
            <details className="task-start-blockers">
              <summary>
                启动前还需完成（{blockers.length}）：检查平台连接与执行条件
              </summary>
              <ul className="blocker-list">
                {blockers.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            </details>
          )}
          {!strategy.available && <label className="check-row">
            <input
              type="checkbox"
              checked={reviewed}
              disabled={starting || strategy.busy || (strategy.available && !strategy.prepared)}
              onChange={(e) =>
                setVerified(e.target.checked ? reviewKey : null)
              }
            />
            我已核对以上业务画像、搜索条件、账号与运行设置
          </label>}
          {action.error && <Notice tone="error">{action.error}</Notice>}
          {nativeMonitor && <Notice action={<Button onClick={()=>navigate('/monitors')}>查看监控任务与原请求</Button>}>
            保存并接管后，在客户端在线期间按已确认周期采集；关闭客户端不补跑。{monitors.error}
          </Notice>}
          {service.execution && !nativeMonitor && <DesktopExecutionRequests
            key={JSON.stringify([session.userId, session.accountScope])}
            execution={desktopExecution}
            canRetryStart={!nativeResearch && strategy.available && strategy.confirmed && reviewed && blockers.length === 0 && !resultUnknown && !starting}
            validateStart={validateDesktopStart}
          />}
          {resultUnknown && (
            <Notice
              tone="warning"
              action={
                <Button
                  onClick={() =>
                    navigate(
                      draft.mode === "monitor" ? "/monitors" : "/collection",
                    )
                  }
                >
                  查看任务列表
                </Button>
              }
            >
              启动结果尚未确认，请先检查任务列表，避免重复创建。
            </Notice>
          )}
          <PendingTaskStarts
            draftId={draft.id}
            onSettled={(status) => {
              action.setError("");
              setVerified(null);
              if (status === "REJECTED")
                setDraft((old) => ({
                  ...old,
                  revision: old.revision + 1,
                  savedAt: null,
                }));
            }}
            onAccepted={(run) => {
              setLibrary((old) => old.filter((item) => item.id !== draft.id));
              navigate(
                run.mode === "monitor"
                  ? `/monitors/${encodeURIComponent(run.id)}`
                  : "/collection",
              );
            }}
          />
          {unresolvedAncestorIds.map((id) => (
            <PendingTaskStarts key={id} draftId={id} />
          ))}
          <div className="task-footer">
            <Button disabled={starting} onClick={() => changeStep(1)}>
              返回修改
            </Button>
            <Button disabled={starting} onClick={save}>
              保存草稿
            </Button>
            <Button
              variant="primary"
              loading={starting}
              disabled={
                blockers.length > 0 || !reviewed || resultUnknown || (strategy.available &&
                  (!strategy.confirmed || (nativeMonitor ? monitors.busy : desktopExecution.blocksStart || desktopExecution.busy)))
              }
              onClick={() => void start()}
            >
              确认并启动
            </Button>
          </div>
        </div>
      )}
      {draft.savedAt && (
        <p className="field-hint">
          本机会话草稿保存于 {formatDate(draft.savedAt)}；关闭客户端或退出登录会清除。
        </p>
      )}
      {preview && (
        <Modal
          title="更新搜索建议"
          onClose={() => setPreview(null)}
          footer={
            <>
              <Button onClick={() => setPreview(null)}>保留当前</Button>
              <Button onClick={() => acceptSuggestion("replace_unedited")}>
                替换未修改的建议
              </Button>
              <Button
                variant="primary"
                onClick={() => acceptSuggestion("append")}
              >
                合并新增建议
              </Button>
            </>
          }
        >
          <p className="muted">
            人工新增、修改和删除的词项会保留，平台与监控设置不会改变。
          </p>
          <h3>搜索关键词</h3>
          <div className="suggestion-list">
            {preview.keywords.map((v, i) => (
              <span key={i}>{v}</span>
            ))}
          </div>
          <h3>排除词</h3>
          <div className="suggestion-list">
            {preview.exclusions.map((v, i) => (
              <span key={i}>{v}</span>
            ))}
          </div>
        </Modal>
      )}
    </>
  );
}
