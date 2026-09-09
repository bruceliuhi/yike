import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest, RequestCancelled } from "../../app/boundedRequest";
import { taskFingerprint } from "../../domain/task";
import { configurationHash } from "../../domain/taskOperations";
import type { TaskDraft } from "../../domain/models";
import {
  parseUsageQuote,
  usageQuoteCurrent,
  usageQuoteRequest,
  type UsageQuote,
} from "../../domain/researchUsage";
import { errorMessage } from "../../services/contracts";

export function useUsageQuote(draft: TaskDraft) {
  const { service, session } = useApp();
  const key = JSON.stringify([
    taskFingerprint(draft),
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
      const input = usageQuoteRequest(
        draft,
        session,
        await configurationHash(draft),
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
    valid: usageQuoteCurrent(visible.quote, draft, session),
    estimate,
    cancel: () => controller.current?.abort(),
  };
}
