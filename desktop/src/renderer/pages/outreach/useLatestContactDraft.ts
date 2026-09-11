import { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import type { Opportunity } from "../../domain/models";
import type { DraftSaveReceipt } from "../../domain/shortCoach";
import { errorMessage } from "../../services/contracts";

export function useLatestContactDraft(
  row: Opportunity,
  channel: "comment" | "dm",
  canAutoApply: boolean,
  onApply: (receipt: DraftSaveReceipt, automatic: boolean) => void,
) {
  const { service, session } = useApp();
  const identity = JSON.stringify([
    session.authenticated,
    session.userId,
    session.accountScope,
    row.id,
    row.profileVersionId,
    row.sourceEvidenceVersion,
    channel,
  ]);
  const live = useRef({ identity, canAutoApply, onApply });
  live.current = { identity, canAutoApply, onApply };
  const enabled =
    session.authenticated &&
    !row.sample &&
    row.id !== "sample" &&
    !!service.contactDrafts?.latest;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    identity: string;
    loading: boolean;
    error: string;
    candidate: DraftSaveReceipt | null;
    complete: boolean;
  }>({ identity, loading: enabled, error: "", candidate: null, complete: !enabled });

  useEffect(() => {
    const latest = service.contactDrafts?.latest;
    if (!session.authenticated || row.sample || row.id === "sample" || !latest) {
      setState({ identity, loading: false, error: "", candidate: null, complete: true });
      return;
    }
    const controller = new AbortController();
    let active = true;
    setState({ identity, loading: true, error: "", candidate: null, complete: false });
    void boundedRequest(
      (signal) => latest(row.id, channel, signal),
      {
        signal: controller.signal,
        timeoutMessage: "读取已保存草稿超时，当前本机内容已保留，请重试。",
      },
    ).then(
      (receipt) => {
        if (!active || live.current.identity !== identity) return;
        if (!receipt) {
          setState({ identity, loading: false, error: "", candidate: null, complete: true });
          return;
        }
        if (
          receipt.status !== "SUCCEEDED" ||
          !receipt.confirmed ||
          !receipt.snapshot ||
          receipt.binding.opportunityId !== row.id ||
          receipt.binding.channel !== channel ||
          receipt.snapshot.draft.opportunityId !== row.id ||
          receipt.snapshot.draft.channel !== channel
        )
          throw new Error("已保存草稿回执无效，当前本机内容已保留。");
        const activeScope = session.accountScope ?? null;
        const savedScope = receipt.snapshot.accountScope;
        if (
          savedScope?.id !== activeScope?.id ||
          savedScope?.version !== activeScope?.version
        )
          throw new Error("已保存草稿不属于当前客户空间，当前本机内容已保留。");
        const sameEvidence =
          receipt.snapshot.profileVersionId === row.profileVersionId &&
          receipt.snapshot.sourceEvidenceVersion === (row.sourceEvidenceVersion || null);
        if (live.current.canAutoApply && sameEvidence) {
          live.current.onApply(receipt, true);
          setState({ identity, loading: false, error: "", candidate: null, complete: true });
        } else {
          setState({ identity, loading: false, error: "", candidate: receipt, complete: true });
        }
      },
    ).catch((error) => {
        if (!active || live.current.identity !== identity) return;
        setState({ identity, loading: false, error: errorMessage(error), candidate: null, complete: false });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [identity, attempt, service]);

  const shown = state.identity === identity
    ? state
    : { identity, loading: enabled, error: "", candidate: null, complete: !enabled };
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const adopt = useCallback(() => {
    if (!shown.candidate || live.current.identity !== identity) return;
    live.current.onApply(shown.candidate, false);
    setState({ identity, loading: false, error: "", candidate: null, complete: true });
  }, [identity, shown.candidate]);
  return { ...shown, retry, adopt };
}
