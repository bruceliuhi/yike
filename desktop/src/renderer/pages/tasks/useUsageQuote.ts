import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest, RequestCancelled } from "../../app/boundedRequest";
import { taskFingerprint } from "../../domain/task";
import { configurationHash, hashText } from "../../domain/taskOperations";
import type {StrategyReceipt} from '../../../shared/researchStrategies';
import type { TaskDraft } from "../../domain/models";
import {
  parseUsageQuote,
  usageQuoteCurrent,
  usageQuoteRequest,
  type UsageQuote,
} from "../../domain/researchUsage";
import { errorMessage } from "../../services/contracts";

interface ConfirmedStrategy {confirmed: boolean; prepared: StrategyReceipt | null; recheck(): Promise<boolean>}
export function useUsageQuote(draft: TaskDraft, strategy?: ConfirmedStrategy) {
  const { service, session } = useApp();
  const key = JSON.stringify([
    taskFingerprint(draft),
    draft.executionLimits,
    service.researchUsage?.requiresConfirmedStrategy ? [strategy?.confirmed, strategy?.prepared?.strategy_version_id,
      strategy?.prepared?.configuration_sha256] : null,
    session.userId,
    session.authenticated,
    session.accountScope,
  ]);
  const identity = useMemo(() => ({}), [key, service]);
  const active = useRef(identity);
  active.current = identity;
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const [state, setState] = useState<{
    identity: object;
    quote: UsageQuote | null;
    busy: boolean;
    error: string;
  }>({ identity, quote: null, busy: false, error: "" });
  useEffect(() => {
    generation.current++;
    controller.current?.abort();
    setState({ identity, quote: null, busy: false, error: "" });
    return () => {
      generation.current++;
      controller.current?.abort();
    };
  }, [identity, service]);
  const visible =
    state.identity === identity
      ? state
      : { quote: null, busy: false, error: "" };
  useEffect(() => {
    if (!visible.quote) return;
    const timer = setTimeout(
      () =>
        setState((old) =>
          old.identity === identity
            ? { ...old, quote: null, error: "本次估算已过期，请重新估算。" }
            : old,
        ),
      Math.max(0, Date.parse(visible.quote.expiresAt) - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [visible.quote, identity]);
  const estimate = async () => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const run = ++generation.current;
    const current = () =>
      active.current === identity && generation.current === run;
    setState({ identity, quote: null, busy: true, error: "" });
    try {
      if (!service.researchUsage)
        throw new Error("用量估算服务尚未接通，草稿可以继续编辑和保存。");
      const prepared = strategy?.prepared;
      const requiresStrategy = service.researchUsage.requiresConfirmedStrategy === true;
      if (requiresStrategy && (!strategy?.confirmed || !prepared || prepared.draft_id !== draft.id ||
          prepared.draft_revision !== draft.revision || prepared.profile_version_id !== draft.profileId ||
          prepared.snapshot.max_records !== draft.executionLimits?.max_records ||
          prepared.snapshot.max_runtime_seconds !== draft.executionLimits?.max_runtime_seconds || !await strategy.recheck()))
        throw new Error('请先核对并确认当前研究策略，再估算用量。');
      if (!current()) return;
      const binding = requiresStrategy && prepared ? {strategyVersionId: prepared.strategy_version_id,
        profileVersionId: prepared.profile_version_id, configurationSha256: prepared.configuration_sha256} : undefined;
      const localHash = await configurationHash(draft);
      const input = usageQuoteRequest(
        draft,
        session,
        binding ? await hashText(JSON.stringify([localHash, draft.executionLimits, binding])) : localHash,
        binding,
      );
      if (!current()) return;
      const raw = await boundedRequest(
        (signal) =>
          service.researchUsage!.quote(input, structuredClone(draft), signal),
        {
          signal: abort.signal,
          timeoutMessage: "用量估算超时，尚未启动或扣减搜贝，可重试。",
        },
      );
      const quote = parseUsageQuote(raw, input);
      if (current()) setState({ identity, quote, busy: false, error: "" });
    } catch (error) {
      if (current())
        setState({
          identity,
          quote: null,
          busy: false,
          error:
            error instanceof RequestCancelled
              ? "已取消估算，现有配置已保留。"
              : errorMessage(error),
        });
    }
  };
  return {
    ...visible,
    valid: usageQuoteCurrent(visible.quote, draft, session) &&
      (!service.researchUsage?.requiresConfirmedStrategy || strategy?.confirmed === true),
    estimate,
    cancel: () => controller.current?.abort(),
  };
}
