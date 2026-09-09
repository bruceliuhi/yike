import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest, RequestCancelled } from "../../app/boundedRequest";
import type { ContactDraft, Opportunity } from "../../domain/models";
import {
  coachSourceKey,
  coachSourceProblem,
  makeCoachInput,
  readCoachSuggestion,
  type CoachInput,
  type CoachPurpose,
  type CoachSuggestion,
} from "../../domain/shortCoach";
import { errorMessage } from "../../services/contracts";

export function useShortCoach(
  row: Opportunity,
  draft: ContactDraft,
  purpose: CoachPurpose,
  apply: (content: string) => void,
) {
  const { service, session } = useApp();
  const scope = JSON.stringify([
    session.authenticated,
    session.userId,
    session.accountScope,
    coachSourceKey(row),
    draft.channel,
    purpose,
  ]);
  const live = useRef({ scope, service, draft });
  live.current = { scope, service, draft };
  const mounted = useRef(true);
  const request = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const [state, setState] = useState<{
    scope: string;
    phase: "idle" | "loading" | "ready" | "applying" | "error";
    input?: CoachInput;
    candidate?: CoachSuggestion;
    error: string;
  }>({ scope, phase: "idle", error: "" });
  const [adopted, setAdopted] = useState<{
    scope: string;
    service: typeof service;
    version: number;
    candidate: CoachSuggestion;
  } | null>(null);
  const adoptedCurrent =
    adopted &&
    adopted.scope === scope &&
    adopted.service === service &&
    adopted.version === draft.version &&
    adopted.candidate.content === draft.content &&
    Date.parse(adopted.candidate.expiresAt) > Date.now()
      ? adopted.candidate
      : null;
  useEffect(() => {
    if (adopted && !adoptedCurrent) setAdopted(null);
  }, [adopted, adoptedCurrent]);
  useEffect(() => {
    if (!adopted) return;
    const timer = setTimeout(
      () => setAdopted((old) => (old === adopted ? null : old)),
      Math.max(
        0,
        Math.min(
          Date.parse(adopted.candidate.expiresAt) - Date.now() + 1,
          2147483647,
        ),
      ),
    );
    return () => clearTimeout(timer);
  }, [adopted]);
  const current = () =>
    mounted.current &&
    live.current.scope === scope &&
    live.current.service === service;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      request.current++;
      abort.current?.abort();
    };
  }, []);
  useEffect(() => {
    request.current++;
    abort.current?.abort();
    lock.current = false;
    setState({ scope, phase: "idle", error: "" });
  }, [scope, service]);
  const shown =
    state.scope === scope
      ? state
      : { scope, phase: "idle" as const, error: "" };
  const generate = async () => {
    if (
      lock.current ||
      !current() ||
      !session.authenticated ||
      row.sample ||
      row.id === "sample"
    )
      return;
    const problem =
      coachSourceProblem(row) ||
      (!session.accountScope
        ? "客户空间版本尚未确认，请重新登录或刷新后再使用短句教练。"
        : "");
    if (!service.shortCoach || problem) {
      setState({
        scope,
        phase: "error",
        error: problem || "短句教练服务尚未接通，可继续编辑或使用原草稿生成。",
      });
      return;
    }
    const generation = ++request.current;
    lock.current = true;
    const controller = new AbortController();
    abort.current = controller;
    setState({ scope, phase: "loading", error: "" });
    try {
      const result = await boundedRequest(
        async (signal) => {
          const input = await makeCoachInput(
            row,
            draft,
            purpose,
            crypto.randomUUID(),
            session.accountScope!,
          );
          if (!current() || signal.aborted) throw new RequestCancelled();
          return {
            input,
            raw: await service.shortCoach!.generate(input, signal),
          };
        },
        {
          signal: controller.signal,
          timeoutMessage:
            "短句建议生成超时，当前内容已保留。可以重新生成，不会应用迟到建议。",
        },
      );
      if (
        !current() ||
        generation !== request.current ||
        controller.signal.aborted
      )
        return;
      const candidate = readCoachSuggestion(result.raw, result.input);
      setState({
        scope,
        phase: "ready",
        input: result.input,
        candidate,
        error: "",
      });
    } catch (error) {
      if (current() && generation === request.current)
        setState({
          scope,
          phase: "error",
          error:
            error instanceof RequestCancelled
              ? "已停止等待，当前内容已保留；没有应用建议。"
              : errorMessage(error),
        });
    } finally {
      if (generation === request.current) lock.current = false;
    }
  };
  const applyCandidate = async () => {
    if (
      lock.current ||
      !current() ||
      !session.authenticated ||
      !shown.candidate ||
      !shown.input
    )
      return;
    const candidate = shown.candidate,
      input = shown.input;
    const atDraft = { version: draft.version, content: draft.content };
    lock.current = true;
    const generation = ++request.current;
    const controller = new AbortController();
    abort.current = controller;
    setState({ ...shown, phase: "applying", error: "" });
    try {
      readCoachSuggestion(candidate, input);
      const fresh = await boundedRequest(() => service.opportunity(row.id), {
        signal: controller.signal,
        timeoutMessage: "引用核对超时，尚未替换当前草稿。",
      });
      if (
        !current() ||
        generation !== request.current ||
        controller.signal.aborted
      )
        return;
      if (
        !fresh ||
        coachSourceProblem(fresh) ||
        coachSourceKey(fresh) !== coachSourceKey(row)
      )
        throw new Error(
          "原文或画像版本已变化，请刷新证据并重新生成；当前文字已保留。",
        );
      readCoachSuggestion(candidate, input);
      if (
        live.current.draft.version !== atDraft.version ||
        live.current.draft.content !== atDraft.content
      )
        throw new Error("核对期间你又修改了草稿，请重新比较后再决定替换。");
      apply(candidate.content);
      setAdopted({ scope, service, version: atDraft.version + 1, candidate });
      setState({ scope, phase: "idle", error: "" });
    } catch (error) {
      if (current() && generation === request.current)
        setState({ ...shown, phase: "ready", error: errorMessage(error) });
    } finally {
      if (generation === request.current) lock.current = false;
    }
  };
  return {
    ...shown,
    adopted: adoptedCurrent,
    generate,
    applyCandidate,
    busy: shown.phase === "loading" || shown.phase === "applying",
    cancel: () => abort.current?.abort(),
    dismiss: () => {
      if (!lock.current) setState({ scope, phase: "idle", error: "" });
    },
  };
}
